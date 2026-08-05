"""Validate factor evaluation and stock selection pipeline.

1. Factor audit (evaluate_factors): scores all factors, marks active/inactive.
2. Stock selection (select_tradable): uses active factors to pick stocks.
3. Backtest: compare strategy performance with/without dynamic stock pool.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import BacktestEngine
from config.loader import load_config
from context.stock_selector import evaluate_factors, select_tradable
from data import validate_ohlcv
from data.fetcher import fetch_daily
from data.filters import detect_limit_price, detect_suspension
from data.storage import load_parquet, save_parquet
from factors.registry import calc_factors
from portfolio.allocator import equal_weight
from risk.position_limit import apply_position_limit
from risk.tradability import enforce_t1, filter_tradable
from strategies.builtin.volume_price_gtja import GTJAVolumePriceStrategy

# ── Config ──────────────────────────────────────────────────────────────
cfg = load_config(Path(__file__).resolve().parent.parent / "configs" / "default.yaml")
SUBSET = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "688256", "002371",
    "600941", "300308", "000063", "600519", "000858", "000333",
    "600276", "300760", "600900", "601985", "300750", "002594",
    "601138", "002475", "600150", "601668", "600031", "002352",
]
START, END = "2023-01-01", "2026-05-24"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

ALL_FACTORS = [
    "calc_money_flow_6d",
    "calc_up_down_vol_ratio_26d",
    "calc_obv_6d",
    "calc_momentum_20d_return",
    "calc_return_1d_times_vol",
]

STRATEGY_NAME = "gtja_volume_price"

# ── Load data ────────────────────────────────────────────────────────────
print("=" * 70)
print("Factor Audit + Stock Selection Validation")
print("=" * 70)

print(f"\nLoading {len(SUBSET)} stocks ({START} ~ {END})...", flush=True)
t0 = time.time()
frames = []
for code in SUBSET:
    path = RAW_DIR / f"{code}.parquet"
    if path.exists():
        frames.append(load_parquet(path))
    else:
        try:
            df = fetch_daily(code, START, END)
            save_parquet(df, path)
            frames.append(df)
        except Exception:
            continue

data = pd.concat(frames, ignore_index=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
prices = data[["date", "code", "close"]]
n_dates = data["date"].nunique()
print(f"  {data['code'].nunique()} stocks, {n_dates} trading days ({time.time() - t0:.1f}s)", flush=True)

# ── Step 1: Factor Audit ─────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Step 1: Factor Audit (evaluate_factors)")
print(f"{'─' * 70}")

t0 = time.time()
factor_df = calc_factors(data, ALL_FACTORS)
audit = evaluate_factors(
    factor_df, ALL_FACTORS,
    lookback=60, lag=5,
    min_coverage=0.8, min_stability=0.3, min_dispersion=0.10,
)
print(audit.to_string(index=False))
print(f"\n  ({time.time() - t0:.1f}s)")

active_factors = audit[audit["active"]]["factor"].tolist()
inactive_factors = audit[~audit["active"]]["factor"].tolist()
print(f"\n  Active:   {active_factors}")
print(f"  Inactive: {inactive_factors}")

# ── Step 2: Stock Selection ──────────────────────────────────────────────
print(f"\n{'─' * 70}")
print(f"Step 2: Stock Selection (select_tradable, {len(active_factors)} active factors)")
print(f"{'─' * 70}")

t0 = time.time()
dynamic_pool = select_tradable(
    factor_df,
    active_factors,
    lookback=60, lag=5,
    min_coverage=0.8, min_stability=0.3, min_dispersion=0.10,
    min_stocks=5, top_n=None,
)
n_pool_dates = len(dynamic_pool)
avg_pool = sum(len(v) for v in dynamic_pool.values()) / max(n_pool_dates, 1)
print(f"  {n_pool_dates}/{n_dates} dates with pool, avg {avg_pool:.1f} stocks ({time.time() - t0:.1f}s)")

# ── Step 3: Backtest Comparison ──────────────────────────────────────────
print(f"\n{'─' * 70}")
print(f"Step 3: Backtest — {STRATEGY_NAME}")
print(f"{'─' * 70}")


def apply_pool_filter(signals: pd.DataFrame, pool: dict) -> pd.DataFrame:
    result = signals.copy()
    for date, allowed in pool.items():
        mask = (result["date"] == date) & (~result["code"].isin(allowed))
        result.loc[mask, "signal"] = 0
        result.loc[mask, "confidence"] = 0.0
    return result


strategy = GTJAVolumePriceStrategy(rebalance=20, top_n=5, bottom_n=3)
signals = strategy.generate_signal(data)
filtered_signals = apply_pool_filter(signals, dynamic_pool)


def backtest(sig: pd.DataFrame, label: str) -> dict:
    f = filter_tradable(data, sig)
    f = enforce_t1(f)
    pos = equal_weight(f, prices, capital=1_000_000)
    pos = apply_position_limit(pos, max_weight=0.3)
    engine = BacktestEngine(capital=1_000_000)
    m = engine.run(pos, prices)["metrics"]
    keys = ["total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "trade_count"]
    return {"label": label, **{k: m[k] for k in keys}}


r_fixed = backtest(signals, "fixed")
r_dyn = backtest(filtered_signals, "dynamic")

print(f"\n  {'':<15} {'Fixed Pool':>12} {'Dynamic Pool':>12} {'Δ':>12}")
for key, fmt in [("total_return", ".1f%%"), ("annual_return", ".2f%%"),
                  ("sharpe_ratio", ".2f"), ("max_drawdown", ".2f%%"),
                  ("win_rate", ".1f%%"), ("trade_count", ".0f")]:
    vf = r_fixed[key]
    vd = r_dyn[key]
    if key in ("trade_count",):
        print(f"  {key:<15} {vf:>12.0f} {vd:>12.0f} {vd - vf:>+12.0f}")
    elif key == "sharpe_ratio":
        print(f"  {key:<15} {vf:>12.2f} {vd:>12.2f} {vd - vf:>+12.2f}")
    else:
        print(f"  {key:<15} {vf*100:>11.1f}% {vd*100:>11.1f}% {(vd - vf)*100:>+11.1f}%")

# ── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Summary")
print(f"{'─' * 70}")
print(f"  Factors audited:    {len(ALL_FACTORS)}")
print(f"  Active:             {len(active_factors)} {active_factors}")
print(f"  Inactive (noise):   {len(inactive_factors)} {inactive_factors}")
print(f"  Pool dates:         {n_pool_dates}/{n_dates}")
print(f"  Avg pool size:      {avg_pool:.1f} stocks")
print(f"  Active-only share:  {avg_pool / data['code'].nunique() * 100:.0f}%")
