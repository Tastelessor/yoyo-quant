"""Compare stock_selector impact on walk-forward backtest.

Experiments:
1. CSI 300 baseline — static universe, no selector
2. Full market + stock_selector (top_n=50)
3. Full market + stock_selector (top_n=100)

Output: metrics comparison table.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.walk_forward import walk_forward_backtest
from config.loader import build_stock_selector, load_config
from data import validate_ohlcv
from data.fetcher import fetch_daily_batch
from data.filters import detect_limit_price, detect_suspension
from data.universe import resolve_universe
from factors.registry import calc_factors
from strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

FACTORS = [
    "calc_money_flow_6d",
    "calc_up_down_vol_ratio_26d",
    "calc_obv_6d",
    "calc_momentum_20d_return",
    "calc_return_1d_times_vol",
]


def make_signal_fn(strategy_name: str, **params):
    """Create a signal_fn for walk_forward_backtest."""
    def signal_fn(train_data, test_data):
        strategy = get_strategy(strategy_name, **params)
        return strategy.generate_signal(test_data)
    return signal_fn


def run_experiment(
    data, signal_fn, label, stock_selector_fn=None,
    train_months=12, test_months=3,
):
    """Run walk-forward backtest and return summary metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=train_months, test_months=test_months,
        stock_selector_fn=stock_selector_fn,
    )
    elapsed = time.time() - t0

    pp = result["per_period"]
    ov = result["overall"]

    if pp.empty:
        return {"label": label, "periods": 0, "elapsed": elapsed}

    return {
        "label": label,
        "periods": len(pp),
        "total_return": ov["total_return"],
        "annual_return": ov["annual_return"],
        "sharpe_ratio": ov["sharpe_ratio"],
        "max_drawdown": ov["max_drawdown"],
        "win_rate": pp["win_rate"].mean(),
        "trade_count": pp["trade_count"].sum(),
        "elapsed": elapsed,
    }


# ── Load configs ─────────────────────────────────────────────────────────
print("=" * 70)
print("Stock Selector Comparison Experiment")
print("=" * 70)

cfg_default = load_config(PROJECT_ROOT / "configs" / "default.yaml")
cfg_full = load_config(
    PROJECT_ROOT / "configs" / "experiment_stock_selector.yaml"
)

# ── Load CSI 300 data ────────────────────────────────────────────────────
print("\n[1/4] Loading CSI 300 data...", flush=True)
codes_csi300 = resolve_universe(cfg_default["universe"])
start = cfg_default["universe"]["start_date"]
end = cfg_default["universe"]["end_date"]
t0 = time.time()
data_csi300 = fetch_daily_batch(
    codes_csi300, start, end, RAW_DIR, sleep_sec=0, progress=True
)
data_csi300 = detect_limit_price(data_csi300)
data_csi300 = detect_suspension(data_csi300)
validate_ohlcv(data_csi300)
n_stocks = data_csi300["code"].nunique()
n_days = data_csi300["date"].nunique()
print(f"  {n_stocks} stocks, {n_days} days ({time.time()-t0:.1f}s)")

# ── Load full market data ────────────────────────────────────────────────
print("\n[2/4] Loading full market data...", flush=True)
codes_full = resolve_universe(cfg_full["universe"])
t0 = time.time()
data_full = fetch_daily_batch(
    codes_full, start, end, RAW_DIR, sleep_sec=0, progress=True
)
data_full = detect_limit_price(data_full)
data_full = detect_suspension(data_full)
validate_ohlcv(data_full)
n_stocks = data_full["code"].nunique()
n_days = data_full["date"].nunique()
print(f"  {n_stocks} stocks, {n_days} days ({time.time()-t0:.1f}s)")

# ── Compute factors ──────────────────────────────────────────────────────
print("\n[3/4] Computing factors...", flush=True)
t0 = time.time()
factor_csi300 = calc_factors(data_csi300, FACTORS)
factor_full = calc_factors(data_full, FACTORS)
print(f"  Done ({time.time()-t0:.1f}s)")

# Merge factor columns into data for walk_forward
for fcol in FACTORS:
    data_csi300 = data_csi300.merge(
        factor_csi300[["date", "code", fcol]], on=["date", "code"], how="left"
    )
    data_full = data_full.merge(
        factor_full[["date", "code", fcol]], on=["date", "code"], how="left"
    )

# ── Build stock selectors ───────────────────────────────────────────────
selector_50 = build_stock_selector({
    "stock_selector": {**cfg_full["stock_selector"], "top_n": 50}
})

# ── Run experiments ──────────────────────────────────────────────────────
print("\n[4/4] Running walk-forward backtests...", flush=True)

signal_fn = make_signal_fn(
    "gtja_momentum", rebalance=10, top_n=5, bottom_n=3
)

results = []

n_csi300 = data_csi300["code"].nunique()
n_full = data_full["code"].nunique()
print(f"  Pool sizes: CSI 300={n_csi300}, Full market={n_full}")

print("  Experiment 1: CSI 300 baseline...", flush=True)
r1 = run_experiment(data_csi300, signal_fn, f"CSI 300 ({n_csi300} stocks)")
results.append(r1)

print("  Experiment 2: 可投池 (no selector)...", flush=True)
r2 = run_experiment(data_full, signal_fn, f"可投池 no selector ({n_full} stocks)")
results.append(r2)

print("  Experiment 3: 可投池 + stock_selector top50...", flush=True)
r3 = run_experiment(
    data_full, signal_fn, "可投池 + selector top50",
    stock_selector_fn=selector_50,
)
results.append(r3)

# ── Results table ────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Results")
print(f"{'=' * 70}\n")

df = pd.DataFrame(results)
fmt_cols = {
    "total_return": ".1%",
    "annual_return": ".2%",
    "sharpe_ratio": ".2f",
    "max_drawdown": ".1%",
    "win_rate": ".1%",
    "trade_count": ".0f",
    "elapsed": ".1f",
}

header = f"{'Label':<25}"
for col in fmt_cols:
    header += f" {col:>14}"
print(header)
print("-" * len(header))

for _, row in df.iterrows():
    line = f"{row['label']:<25}"
    for col, fmt in fmt_cols.items():
        if col in row:
            line += f" {row[col]:>14{fmt}}"
        else:
            line += f" {'N/A':>14}"
    print(line)

print(f"\n{'=' * 70}")
print("Done.")
