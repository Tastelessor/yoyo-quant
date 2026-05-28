"""Compare factor-level industry neutralization impact on walk-forward backtest.

Experiments:
1. Baseline (no neutralization)
2. Neutralization enabled (min_peers=3)

Output: metrics comparison table + per-strategy breakdown.
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
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_signal_fn(strategy_name: str, industry_map=None, min_peers=3, **params):
    """Create a signal_fn for walk_forward_backtest."""
    def signal_fn(train_data, test_data):
        kwargs = dict(params)
        if industry_map is not None:
            kwargs["industry_map"] = industry_map
            kwargs["min_peers"] = min_peers
        strategy = get_strategy(strategy_name, **kwargs)
        return strategy.generate_signal(test_data)
    return signal_fn


def run_experiment(data, signal_fn, label, train_months=12, test_months=3):
    """Run walk-forward backtest and return summary metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=train_months, test_months=test_months,
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


def compute_industry_concentration(data, signal_fn, industry_map):
    """Compute average number of unique industries in buy signals."""
    signal_df = signal_fn(data, data)
    buys = signal_df[signal_df["signal"] == 1]
    if buys.empty:
        return 0.0
    # Per-date industry count
    daily = buys.groupby("date")["code"].apply(
        lambda codes: len({industry_map.get(c, "?") for c in codes})
    )
    return daily.mean()


# ── Load config ──────────────────────────────────────────────────────────
print("=" * 70)
print("Factor-Level Industry Neutralization A/B Experiment")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "default.yaml")

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
all_stocks_df = fetch_all_stocks()
industry_map = dict(zip(all_stocks_df["code"], all_stocks_df["industry"]))
data_industries = {industry_map.get(c, "其他") for c in data["code"].unique()}
print(f"  {len(data_industries)} industries in universe")

# ── Define strategies to test ────────────────────────────────────────────
print("\n[3/4] Preparing strategies...", flush=True)

strategies = [
    ("gtja_momentum", {"rebalance": 10, "top_n": 5, "bottom_n": 3}),
    ("reversed_gtja_vwap", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_mean_reversion", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_volume_price", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_trend", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_volatility", {"rebalance": 5, "top_n": 3, "bottom_n": 3}),
]

# ── Run experiments ──────────────────────────────────────────────────────
print("\n[4/4] Running walk-forward backtests...", flush=True)

results = []
for strat_name, params in strategies:
    print(f"\n  {strat_name}:", flush=True)

    # Baseline
    print(f"    Baseline...", end=" ", flush=True)
    fn_raw = make_signal_fn(strat_name, **params)
    r_raw = run_experiment(data, fn_raw, f"{strat_name} (raw)")
    print(f"Sharpe={r_raw.get('sharpe_ratio', 0):.3f}", flush=True)

    # With neutralization
    print(f"    Neutralized...", end=" ", flush=True)
    fn_neut = make_signal_fn(strat_name, industry_map=industry_map,
                             min_peers=3, **params)
    r_neut = run_experiment(data, fn_neut, f"{strat_name} (neutral)")
    print(f"Sharpe={r_neut.get('sharpe_ratio', 0):.3f}", flush=True)

    # Industry concentration
    conc_raw = compute_industry_concentration(data, fn_raw, industry_map)
    conc_neut = compute_industry_concentration(data, fn_neut, industry_map)

    r_raw["ind_concentration"] = conc_raw
    r_neut["ind_concentration"] = conc_neut

    results.append(r_raw)
    results.append(r_neut)

# ── Results table ────────────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print("Results Summary")
print(f"{'=' * 90}\n")

df = pd.DataFrame(results)
fmt_cols = {
    "total_return": ".1%",
    "annual_return": ".2%",
    "sharpe_ratio": ".3f",
    "max_drawdown": ".1%",
    "win_rate": ".1%",
    "trade_count": ".0f",
    "ind_concentration": ".1f",
    "elapsed": ".1f",
}

header = f"{'Label':<35}"
for col in fmt_cols:
    header += f" {col:>15}"
print(header)
print("-" * len(header))

for _, row in df.iterrows():
    line = f"{row['label']:<35}"
    for col, fmt in fmt_cols.items():
        if col in row:
            line += f" {row[col]:>15{fmt}}"
        else:
            line += f" {'N/A':>15}"
    print(line)

# ── Delta table ──────────────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print("Delta: Neutralized - Raw")
print(f"{'=' * 90}\n")

for strat_name, _ in strategies:
    raw = next(r for r in results if r["label"] == f"{strat_name} (raw)")
    neut = next(r for r in results if r["label"] == f"{strat_name} (neutral)")
    d_sharpe = neut["sharpe_ratio"] - raw["sharpe_ratio"]
    d_mdd = neut["max_drawdown"] - raw["max_drawdown"]
    d_conc = neut["ind_concentration"] - raw["ind_concentration"]
    print(f"  {strat_name:<30} Sharpe: {d_sharpe:+.3f}  MaxDD: {d_mdd:+.1%}  IndConc: {d_conc:+.1f}")

print(f"\n{'=' * 90}")
print("Done.")
