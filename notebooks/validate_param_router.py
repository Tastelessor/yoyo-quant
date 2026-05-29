"""Validate parameter routing: walk-forward comparison of fixed vs routed params.

Usage: python notebooks/validate_param_router.py

Compares two RegimeSwitchStrategy variants on walk-forward backtest:
  1. FIXED:  all regimes use the same params (rebalance=20, top_n=5, bottom_n=3)
  2. ROUTED: each regime routes to different params via param_router

If ROUTED > FIXED on Sharpe/MaxDD, parameter routing adds value.
If ROUTED ≈ FIXED, regime-aware params don't move the needle.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.walk_forward import walk_forward_backtest
from src.context.param_router import DEFAULT_REGIME_PARAMS, route_params
from src.context.regime import detect_regime
from src.context.regime_switch import RegimeSwitchStrategy
from src.data.fetcher import fetch_daily
from src.data.filters import detect_limit_price, detect_suspension
from src.data.storage import load_parquet, save_parquet
from src.strategies.registry import get_strategy

PROJECT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT / "data" / "raw"

# ── Config ──────────────────────────────────────────────────────────────
CODES = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "688256", "002371",
    "600941", "300308", "000063", "600519", "000858", "000333",
    "600276", "300760",
]
START, END = "2023-01-01", "2026-05-24"
CAPITAL = 1_000_000
MAX_WEIGHT = 0.3

# Regime → strategy mapping (fixed for both variants)
REGIME_STRATEGY = {
    "trend_up":    "gtja_momentum",
    "trend_down":  "reversed_gtja_vwap",
    "range":       "reversed_gtja_vwap",
    "volatile":    "gtja_volatility",
}

# FIXED params (baseline)
FIXED_PARAMS = {"rebalance": 20, "top_n": 5, "bottom_n": 3}

# ROUTED params (from param_router)
ROUTED_PARAMS = DEFAULT_REGIME_PARAMS


def build_regime_switch(params_map: dict[str, dict]) -> RegimeSwitchStrategy:
    """Build a RegimeSwitchStrategy with per-regime params."""
    regimes = {}
    for regime_label, strategy_name in REGIME_STRATEGY.items():
        p = params_map.get(regime_label, FIXED_PARAMS)
        regimes[regime_label] = get_strategy(strategy_name, **p)
    return RegimeSwitchStrategy(regimes=regimes)


# ── Build both strategies ──────────────────────────────────────────────
fixed_rs = build_regime_switch({r: FIXED_PARAMS for r in REGIME_STRATEGY})
routed_rs = build_regime_switch(ROUTED_PARAMS)


def make_signal_fn(rs: RegimeSwitchStrategy):
    """Create a signal_fn compatible with walk_forward_backtest."""
    def signal_fn(train_data, test_data):
        # Concatenate for lookback (regime detection + strategy need history)
        all_data = pd.concat([train_data, test_data], ignore_index=True)
        all_data = all_data.sort_values(["code", "date"]).reset_index(drop=True)
        signals = rs.generate_signal(all_data)
        # Return only test-period signals
        test_dates = set(test_data["date"].unique())
        return signals[signals["date"].isin(test_dates)].copy()
    return signal_fn


# ── Load data ──────────────────────────────────────────────────────────
print("=" * 70)
print("Parameter Routing Validation: Walk-Forward Backtest")
print("=" * 70)

print(f"\n[1/3] Loading {len(CODES)} stocks ({START} ~ {END})...", end=" ", flush=True)
t0 = time.time()
frames = []
for code in CODES:
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
n_stocks = data["code"].nunique()
n_days = data["date"].nunique()
print(f"{n_stocks} stocks, {n_days} days ({time.time() - t0:.0f}s)")

# ── Run walk-forward ───────────────────────────────────────────────────
WF_PARAMS = {
    "train_months": 12,
    "test_months": 3,
    "capital": CAPITAL,
    "max_weight": MAX_WEIGHT,
}

print(f"\n[2/3] Walk-forward: FIXED params (rebalance=20, top_n=5)...", flush=True)
t0 = time.time()
fixed_wf = walk_forward_backtest(
    data, make_signal_fn(fixed_rs), **WF_PARAMS,
)
fixed_pp = fixed_wf["per_period"]
fixed_ov = fixed_wf["overall"]
n_periods = len(fixed_pp)
print(f"  {n_periods} periods ({time.time() - t0:.0f}s)")

print(f"\n[3/3] Walk-forward: ROUTED params (per-regime)...", flush=True)
t0 = time.time()
routed_wf = walk_forward_backtest(
    data, make_signal_fn(routed_rs), **WF_PARAMS,
)
routed_pp = routed_wf["per_period"]
routed_ov = routed_wf["overall"]
print(f"  {n_periods} periods ({time.time() - t0:.0f}s)")

# ── Comparison ─────────────────────────────────────────────────────────
print(f"\n{'─' * 80}")
print("Walk-Forward Comparison: FIXED vs ROUTED")
print(f"{'─' * 80}")

metrics = ["sharpe_ratio", "annual_return", "max_drawdown", "total_return"]
labels = {"sharpe_ratio": "Sharpe", "annual_return": "Ann.Ret", "max_drawdown": "MaxDD",
          "total_return": "TotalRet"}

print(f"\n{'Period':<10} {'FIXED Sharpe':>13} {'ROUTED Sharpe':>13} {'Δ Sharpe':>10} {'Winner':>8}")
print("-" * 60)
for i in range(n_periods):
    fs = fixed_pp.iloc[i]["sharpe_ratio"]
    rs = routed_pp.iloc[i]["sharpe_ratio"]
    delta = rs - fs
    winner = "ROUTED" if delta > 0 else ("FIXED" if delta < 0 else "TIE")
    print(f"P{i+1:<9} {fs:>13.3f} {rs:>13.3f} {delta:>+10.3f} {winner:>8}")

print(f"\n{'Metric':<14} {'FIXED':>10} {'ROUTED':>10} {'Δ':>10} {'Winner':>8}")
print("-" * 54)
for m in metrics:
    f_val = fixed_ov.get(m, fixed_pp[m].mean())
    r_val = routed_ov.get(m, routed_pp[m].mean())
    delta = r_val - f_val
    winner = "ROUTED" if delta > 0 else ("FIXED" if delta < 0 else "TIE")
    if m == "sharpe_ratio":
        print(f"{labels[m]:<14} {f_val:>10.3f} {r_val:>10.3f} {delta:>+10.3f} {winner:>8}")
    else:
        print(f"{labels[m]:<14} {f_val:>9.2f}% {r_val:>9.2f}% {delta:>+9.2f}% {winner:>8}")

# Count wins
sharpe_wins = 0
for i in range(n_periods):
    fs = fixed_pp.iloc[i]["sharpe_ratio"]
    rs = routed_pp.iloc[i]["sharpe_ratio"]
    if rs > fs:
        sharpe_wins += 1

print(f"\nROUTED wins {sharpe_wins}/{n_periods} periods on Sharpe")

# ── Regime distribution info ───────────────────────────────────────────
print(f"\n{'─' * 80}")
print("Regime-Specific Params Used by ROUTED:")
for regime in ["trend_up", "trend_down", "range", "volatile"]:
    p = ROUTED_PARAMS[regime]
    print(f"  {regime:<14} strategy={REGIME_STRATEGY[regime]:<22} "
          f"rebalance={p['rebalance']}, top_n={p['top_n']}, bottom_n={p['bottom_n']}")
