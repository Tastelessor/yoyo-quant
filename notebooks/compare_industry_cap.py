"""Compare industry cap impact on walk-forward backtest.

Experiments:
1. No industry cap (baseline)
2. Industry cap = 30%
3. Industry cap = 20%
4. Industry cap + momentum tilt

Output: metrics comparison table.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.walk_forward import walk_forward_backtest
from src.config.loader import load_config
from src.data import validate_ohlcv
from src.data.fetcher import fetch_all_stocks, fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.portfolio.industry_momentum import (
    apply_industry_tilt,
    compute_industry_momentum,
)
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_signal_fn(strategy_name: str, **params):
    """Create a signal_fn for walk_forward_backtest."""
    def signal_fn(train_data, test_data):
        strategy = get_strategy(strategy_name, **params)
        return strategy.generate_signal(test_data)
    return signal_fn


def run_experiment(
    data, signal_fn, label, industry_map=None,
    max_industry_weight=0.30, train_months=12, test_months=3,
):
    """Run walk-forward backtest and return summary metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=train_months, test_months=test_months,
        industry_map=industry_map,
        max_industry_weight=max_industry_weight,
    )
    elapsed = time.time() - t0

    if result.empty:
        return {"label": label, "periods": 0, "elapsed": elapsed}

    return {
        "label": label,
        "periods": len(result),
        "total_return": result["total_return"].mean(),
        "annual_return": result["annual_return"].mean(),
        "sharpe_ratio": result["sharpe_ratio"].mean(),
        "max_drawdown": result["max_drawdown"].mean(),
        "win_rate": result["win_rate"].mean(),
        "trade_count": result["trade_count"].mean(),
        "elapsed": elapsed,
    }


# ── Load config ──────────────────────────────────────────────────────────
print("=" * 70)
print("Industry Cap Comparison Experiment")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "experiment_stock_selector.yaml")

# ── Load data ────────────────────────────────────────────────────────────
print("\n[1/4] Loading tradable universe data...", flush=True)
codes = resolve_universe(cfg["universe"])
start = cfg["universe"]["start_date"]
end = cfg["universe"]["end_date"]
t0 = time.time()
data = fetch_daily_batch(codes, start, end, RAW_DIR, sleep_sec=0, progress=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
n_stocks = data["code"].nunique()
n_days = data["date"].nunique()
print(f"  {n_stocks} stocks, {n_days} days ({time.time()-t0:.1f}s)")

# ── Build industry mapping ──────────────────────────────────────────────
print("\n[2/4] Building industry mapping...", flush=True)
all_stocks = fetch_all_stocks(date=cfg["universe"]["fetch_date"])
industry_map = dict(zip(all_stocks["code"], all_stocks["industry"]))
# Count industries in our data
data_industries = {industry_map.get(c, "其他") for c in data["code"].unique()}
print(f"  {len(data_industries)} industries in universe")

# ── Compute industry momentum ───────────────────────────────────────────
print("\n[3/4] Computing industry momentum...", flush=True)
t0 = time.time()
data_with_industry = data.copy()
data_with_industry["industry"] = data_with_industry["code"].map(
    lambda c: industry_map.get(c, "其他")
)
momentum = compute_industry_momentum(data_with_industry, lookback=20)
print(f"  Done ({time.time()-t0:.1f}s)")

# ── Run experiments ──────────────────────────────────────────────────────
print("\n[4/4] Running walk-forward backtests...", flush=True)

signal_fn = make_signal_fn(
    "gtja_momentum", rebalance=10, top_n=5, bottom_n=3
)

results = []

print("  Experiment 1: No industry cap (baseline)...", flush=True)
r1 = run_experiment(data, signal_fn, "No cap (baseline)")
results.append(r1)

print("  Experiment 2: Industry cap = 30%...", flush=True)
r2 = run_experiment(data, signal_fn, "Cap 30%", industry_map=industry_map, max_industry_weight=0.30)
results.append(r2)

print("  Experiment 3: Industry cap = 20%...", flush=True)
r3 = run_experiment(data, signal_fn, "Cap 20%", industry_map=industry_map, max_industry_weight=0.20)
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
