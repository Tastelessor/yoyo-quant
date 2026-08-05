"""CSI 500 continuous backtest — no walk-forward split.

Compare continuous vs walk-forward for earnings_surprise on CSI 500.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.continuous import continuous_backtest
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


# ── Load data ─────────────────────────────────────────────────────────
print("=" * 80)
print("CSI 500: Continuous vs Walk-Forward Comparison")
print("=" * 80)

codes = fetch_index_constituents("000905.SH", date="2026-05-23")
print(f"\n  {len(codes)} CSI 500 constituents")

print(f"  Loading OHLCV...", flush=True)
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=False)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

print("  Loading earnings...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0, progress=False)
trade_dates = fetch_trade_dates(START_DATE, END_DATE)
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  {len(earnings_raw)} events ({time.time()-t0:.1f}s)")

_cfg = load_config(PROJECT_ROOT / "configs" / "production.yaml")
industry_cfg = build_industry_map(_cfg)
industry_map, min_peers = industry_cfg

# ── Experiment 1: Walk-forward (corrected) ────────────────────────────
print(f"\n{'=' * 80}")
print("[1/2] Walk-forward (12m train / 3m test)")
print(f"{'=' * 80}\n")


def wf_signal_fn(train_data, test_data):
    s = get_strategy("gtja_earnings_surprise",
                     rebalance=15, top_n=10, bottom_n=5,
                     industry_map=industry_map, min_peers=min_peers)
    return s.generate_signal(test_data)


t0 = time.time()
wf_result = walk_forward_backtest(
    data, wf_signal_fn,
    train_months=12, test_months=3,
    dead_zone=0.015,
    industry_map=industry_map,
)
wf_elapsed = time.time() - t0

wf_ov = wf_result["overall"]
wf_pp = wf_result["per_period"]

print(f"  Sharpe        = {wf_ov['sharpe_ratio']:.3f}")
print(f"  Annual Return = {wf_ov['annual_return']:.2%}")
print(f"  Total Return  = {wf_ov['total_return']:.2%}")
print(f"  MaxDD         = {wf_ov['max_drawdown']:.2%}")
print(f"  Per-pd Std    = {wf_ov['per_period_sharpe_std']:.3f}")
print(f"  Trades        = {wf_pp['trade_count'].sum():.0f}")
print(f"  Periods       = {len(wf_pp)}")
print(f"  Elapsed       = {wf_elapsed:.1f}s")

# ── Experiment 2: Continuous (single pass) ────────────────────────────
print(f"\n{'=' * 80}")
print("[2/2] Continuous (single pass, no train/test split)")
print(f"{'=' * 80}\n")


def cont_signal_fn(full_data):
    s = get_strategy("gtja_earnings_surprise",
                     rebalance=15, top_n=10, bottom_n=5,
                     industry_map=industry_map, min_peers=min_peers)
    return s.generate_signal(full_data)


t0 = time.time()
cont_result = continuous_backtest(
    data, cont_signal_fn,
    dead_zone=0.015,
    industry_map=industry_map,
)
cont_elapsed = time.time() - t0

cont_ov = cont_result["overall"]
cont_eq = cont_result["equity_curve"]
cont_trades = cont_result["trades"]

print(f"  Sharpe        = {cont_ov['sharpe_ratio']:.3f}")
print(f"  Annual Return = {cont_ov['annual_return']:.2%}")
print(f"  Total Return  = {cont_ov['total_return']:.2%}")
print(f"  MaxDD         = {cont_ov['max_drawdown']:.2%}")
print(f"  Trades        = {len(cont_trades)}")
print(f"  Elapsed       = {cont_elapsed:.1f}s")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("COMPARISON: Walk-Forward vs Continuous")
print(f"{'=' * 80}\n")

header = f"{'Metric':<20} {'Walk-Forward':>15} {'Continuous':>15}"
print(header)
print("-" * len(header))
print(f"{'Sharpe':<20} {wf_ov['sharpe_ratio']:>15.3f} {cont_ov['sharpe_ratio']:>15.3f}")
print(f"{'Annual Return':<20} {wf_ov['annual_return']:>14.2%} {cont_ov['annual_return']:>14.2%}")
print(f"{'Total Return':<20} {wf_ov['total_return']:>14.2%} {cont_ov['total_return']:>14.2%}")
print(f"{'MaxDD':<20} {wf_ov['max_drawdown']:>14.2%} {cont_ov['max_drawdown']:>14.2%}")
print(f"{'Trades':<20} {wf_pp['trade_count'].sum():>15.0f} {len(cont_trades):>15}")

# Per-year breakdown from continuous equity
if not cont_eq.empty:
    eq = cont_eq.copy()
    eq["year"] = pd.to_datetime(eq["date"]).dt.year
    eq["ret"] = eq["equity"].pct_change()
    yearly = eq.groupby("year").apply(
        lambda g: pd.Series({
            "return": (1 + g["ret"]).prod() - 1,
            "maxdd": abs((g["equity"] / g["equity"].cummax() - 1).min()),
        })
    )
    print(f"\n{'=' * 80}")
    print("YEARLY BREAKDOWN (Continuous)")
    print(f"{'=' * 80}\n")
    print(f"{'Year':<8} {'Return':>10} {'MaxDD':>10}")
    print("-" * 30)
    for yr, row in yearly.iterrows():
        print(f"{yr:<8} {row['return']:>9.2%} {row['maxdd']:>9.2%}")

print(f"\n{'=' * 80}")
