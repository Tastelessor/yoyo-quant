"""Rebalance Frequency Sweep — multi-strategy batch scan.

Sweeps rebalance frequencies [5, 10, 15, 20, 30] across multiple strategies.
Outputs:
1. Full table: all combinations sorted by Sharpe descending
2. Per-strategy table: optimal rebalance + Sharpe/IR per strategy
3. Short-alpha diagnostic: which strategies benefit from shorter rebalance
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import TradingCost
from src.backtest.walk_forward import walk_forward_backtest
from src.config.loader import build_industry_map, load_config
from src.data import validate_ohlcv
from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.fetcher import fetch_daily_batch, fetch_index_constituents
from src.data.filters import detect_limit_price, detect_suspension
from src.data.trade_calendar import fetch_trade_dates
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"

REBALANCE_FREQS = [5, 10, 15, 20, 30]

# rebalance=None → injected by sweep loop
STRATEGIES = [
    {"name": "gtja_earnings_surprise", "params": {"top_n": 10, "bottom_n": 5, "rebalance": None}},
    {"name": "gtja_momentum",          "params": {"rebalance": None}},
    {"name": "gtja_volume_price",      "params": {"rebalance": None}},
    {"name": "gtja_volatility",        "params": {"rebalance": None}},
    {"name": "gtja_vwap",              "params": {"rebalance": None}},
]


def make_signal_fn(strategy_name, params, industry_map, min_peers):
    """Build a walk-forward signal_fn for any registered strategy."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        s = get_strategy(strategy_name, **params, **extra)
        return s.generate_signal(test_data)
    return signal_fn


# ═══════════════════════════════════════════════════════════════════════
# Load data (shared across all strategy×rebalance combos)
# ═══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("Rebalance Frequency Sweep — Multi-Strategy Batch Scan")
print("=" * 80)

print("\n[1/4] Fetching CSI 500 constituents...", flush=True)
codes = fetch_index_constituents("000905.SH", date="2026-05-23")
print(f"  {len(codes)} stocks")

print(f"\n[2/4] Loading OHLCV ({START_DATE} to {END_DATE})...", flush=True)
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=False)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

print("\n[3/4] Loading earnings data...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0, progress=False)
trade_dates = fetch_trade_dates(START_DATE, END_DATE)
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  {len(earnings_raw)} events, {time.time()-t0:.1f}s")

print("\n[4/4] Building industry map...", flush=True)
_cfg = load_config(PROJECT_ROOT / "configs" / "production.yaml")
industry_cfg = build_industry_map(_cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped")

# ═══════════════════════════════════════════════════════════════════════
# Sweep: strategy × rebalance
# ═══════════════════════════════════════════════════════════════════════
total_runs = len(STRATEGIES) * len(REBALANCE_FREQS)
print(f"\n{'=' * 80}")
print(f"Sweeping {len(STRATEGIES)} strategies × {len(REBALANCE_FREQS)} frequencies = {total_runs} runs")
print(f"{'=' * 80}\n")

default_tc = TradingCost()  # production defaults
results = []
run_idx = 0

for strat in STRATEGIES:
    name = strat["name"]
    print(f"  [{name}]")
    for rb in REBALANCE_FREQS:
        run_idx += 1
        # Inject rebalance into params
        params = {k: (rb if v is None else v) for k, v in strat["params"].items()}

        print(f"    rb={rb:>2d} ({run_idx}/{total_runs}) ...", end=" ", flush=True)
        t0 = time.time()

        fn = make_signal_fn(name, params, industry_map, min_peers)
        wf_result = walk_forward_backtest(
            data, fn,
            train_months=12, test_months=3,
            dead_zone=0.015,
            industry_map=industry_map,
            trading_cost=default_tc,
        )
        ov = wf_result["overall"]
        pp = wf_result["per_period"]
        elapsed = time.time() - t0

        cost_ratio = pp["cost_ratio"].mean() if "cost_ratio" in pp.columns else 0.0
        trade_count = pp["trade_count"].sum() if "trade_count" in pp.columns else 0

        results.append({
            "strategy": name,
            "rebalance": int(rb),
            "sharpe": ov["sharpe_ratio"],
            "ir": ov["per_period_ir"],
            "max_dd": ov["max_drawdown"],
            "annual_return": ov.get("annual_return", 0.0),
            "cost_ratio": cost_ratio,
            "trade_count": int(trade_count),
            "periods": len(pp),
            "elapsed": elapsed,
        })

        print(f"Sharpe={ov['sharpe_ratio']:.3f}  IR={ov['per_period_ir']:.3f}  "
              f"MaxDD={ov['max_drawdown']:.1%}  ({elapsed:.0f}s)")

# ═══════════════════════════════════════════════════════════════════════
# Table 1: Full results sorted by Sharpe
# ═══════════════════════════════════════════════════════════════════════
df = pd.DataFrame(results).sort_values("sharpe", ascending=False)

print(f"\n{'=' * 80}")
print("TABLE 1: ALL COMBINATIONS (sorted by Sharpe)")
print(f"{'=' * 80}\n")

header = (f"{'Strategy':<24} {'RB':>4} {'Sharpe':>8} {'IR':>8} "
          f"{'MaxDD':>8} {'AnnRet':>8} {'CostR':>8} {'Trades':>7}")
print(header)
print("-" * len(header))
for _, row in df.iterrows():
    print(f"{row['strategy']:<24} {int(row['rebalance']):>4d} "
          f"{row['sharpe']:>8.3f} {row['ir']:>8.3f} "
          f"{row['max_dd']:>7.1%} {row['annual_return']:>7.1%} "
          f"{row['cost_ratio']:>7.2%} {int(row['trade_count']):>7d}")

# ═══════════════════════════════════════════════════════════════════════
# Table 2: Per-strategy best rebalance
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("TABLE 2: PER-STRATEGY OPTIMAL REBALANCE")
print(f"{'=' * 80}\n")

best_per_strategy = (
    df.sort_values("sharpe", ascending=False)
    .groupby("strategy")
    .first()
    .reset_index()
    .sort_values("sharpe", ascending=False)
)

header2 = (f"{'Strategy':<24} {'BestRB':>6} {'Sharpe':>8} {'IR':>8} "
           f"{'MaxDD':>8} {'CostR':>8} {'Trades':>7}")
print(header2)
print("-" * len(header2))
for _, row in best_per_strategy.iterrows():
    print(f"{row['strategy']:<24} {int(row['rebalance']):>6d} "
          f"{row['sharpe']:>8.3f} {row['ir']:>8.3f} "
          f"{row['max_dd']:>7.1%} {row['cost_ratio']:>7.2%} {int(row['trade_count']):>7d}")

# ═══════════════════════════════════════════════════════════════════════
# Short-alpha diagnostic
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("SHORT-ALPHA DIAGNOSTIC: short rb (5-10) vs long rb (15-30)")
print(f"{'=' * 80}\n")

for strat_name in df["strategy"].unique():
    s_df = df[df["strategy"] == strat_name]
    short = s_df[s_df["rebalance"].isin([5, 10])]["sharpe"].mean()
    long_ = s_df[s_df["rebalance"].isin([15, 20, 30])]["sharpe"].mean()
    delta = short - long_
    marker = " ← SHORT ALPHA" if delta > 0.02 else (" ← SHORT HARM" if delta < -0.02 else "")
    print(f"  {strat_name:<24}  short={short:.3f}  long={long_:.3f}  Δ={delta:+.3f}{marker}")

print()
print("  Interpretation:")
print("    SHORT ALPHA (Δ>0.02): factor captures short-term signals, benefits from frequent rebalance")
print("    SHORT HARM  (Δ<-0.02): frequent rebalance adds noise/cost, longer holding is better")
print("    NEUTRAL     (-0.02≤Δ≤0.02): rebalance frequency doesn't materially affect this factor")
