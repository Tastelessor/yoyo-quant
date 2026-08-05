"""Phase 16 backtest: Multi-Silo independent sub-portfolios.

Silo A (Fundamental): earnings-only N=10 rb=15 — 50% capital
Silo B (Quant Twin-star): reversed_vwap + volatility N=25 — 50% capital

Merged at weight level (outer join), single BacktestEngine.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.walk_forward import walk_forward_backtest, walk_forward_multi_silo
from src.config.loader import build_industry_map, load_config
from src.data import validate_ohlcv
from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.fetcher import fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.trade_calendar import fetch_trade_dates
from src.data.universe import resolve_universe
from src.strategies.combiner import WeightedVoteCombiner
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                             industry_map=None, min_peers=3):
    """Silo A: earnings-only strategy."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        s = get_strategy("gtja_earnings_surprise",
                         rebalance=rebalance, top_n=top_n, bottom_n=bottom_n, **extra)
        return s.generate_signal(test_data)
    return signal_fn


def make_twin_star_signal_fn(top_n=25, bottom_n=12, industry_map=None, min_peers=3):
    """Silo B: twin-star quant strategy (reversed_vwap + volatility)."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        vwap = get_strategy("reversed_gtja_vwap",
                            rebalance=20, top_n=top_n, bottom_n=bottom_n, **extra)
        vol = get_strategy("gtja_volatility",
                           rebalance=20, top_n=top_n, bottom_n=bottom_n, **extra)
        combiner = WeightedVoteCombiner([(vwap, 0.52), (vol, 0.48)], threshold=0.5)
        return combiner.combine(test_data)
    return signal_fn


def run_experiment(data, signal_fn_or_silos, label, dead_zone, is_multi_silo=False,
                   industry_map=None, max_industry_weight=0.30, **wf_kwargs):
    """Run walk-forward and return metrics."""
    t0 = time.time()
    if is_multi_silo:
        result = walk_forward_multi_silo(
            data, signal_fn_or_silos,
            train_months=12, test_months=3,
            dead_zone=dead_zone,
            industry_map=industry_map,
            max_industry_weight=max_industry_weight,
            **wf_kwargs,
        )
    else:
        result = walk_forward_backtest(
            data, signal_fn_or_silos,
            train_months=12, test_months=3,
            dead_zone=dead_zone,
            **wf_kwargs,
        )
    elapsed = time.time() - t0

    pp = result["per_period"]
    overall = result["overall"]

    if pp.empty or len(pp) < 2:
        return {"label": label, "periods": 0, "elapsed": elapsed}

    return {
        "label": label,
        "periods": len(pp),
        "total_return": overall["total_return"],
        "annual_return": overall["annual_return"],
        "sharpe_ratio": overall["sharpe_ratio"],
        "sharpe_std": overall["per_period_sharpe_std"],
        "max_drawdown": overall["max_drawdown"],
        "trade_count": pp["trade_count"].sum(),
        "elapsed": elapsed,
    }


# ── Load data ─────────────────────────────────────────────────────────
print("=" * 80)
print("Phase 16: Multi-Silo Independent Sub-Portfolios")
print("=" * 80)

cfg = load_config(PROJECT_ROOT / "configs" / "production.yaml")

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"

print(f"\n[1/4] Loading OHLCV ({START_DATE} to {END_DATE})...", flush=True)
codes = resolve_universe(cfg["universe"])
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=False)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

print("\n[2/4] Loading earnings data (cached)...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0, progress=False)
trade_dates = fetch_trade_dates(START_DATE, END_DATE)
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  {len(earnings_raw)} events, {time.time()-t0:.1f}s")

print("\n[3/4] Building industry map...", flush=True)
industry_cfg = build_industry_map(cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped")

# ── Run experiments ────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("[4/4] Running experiments...")
print(f"{'=' * 80}\n")

results = []

# Baseline 1: twin-star (original production)
print("  [1/6] twin-star baseline...", flush=True)
fn_ts = make_twin_star_signal_fn(top_n=5, bottom_n=3, industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_ts, "twin-star/N5", dead_zone=0.01)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# Baseline 2: earnings-only N=10 rb=15
print("  [2/6] earnings-only N=10 rb=15...", flush=True)
fn_earn = make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                   industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_earn, "earn-only/N10/rb15", dead_zone=0.015)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# Baseline 3: twin-star N=25 (larger pool for silo B)
print("  [3/6] twin-star N=25...", flush=True)
fn_ts25 = make_twin_star_signal_fn(top_n=25, bottom_n=12, industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_ts25, "twin-star/N25", dead_zone=0.015)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# Multi-Silo: 50/50 earnings + twin-star
print("  [4/6] multi-silo 50/50 (earn + twin-star)...", flush=True)
silos_50_50 = [
    {"signal_fn": make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                           industry_map=industry_map, min_peers=min_peers),
     "weight": 0.50, "name": "fundamental"},
    {"signal_fn": make_twin_star_signal_fn(top_n=25, bottom_n=12,
                                            industry_map=industry_map, min_peers=min_peers),
     "weight": 0.50, "name": "quant"},
]
r = run_experiment(data, silos_50_50, "multi-silo/50-50", dead_zone=0.015, is_multi_silo=True,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# Multi-Silo: 60/40 earnings-heavy
print("  [5/6] multi-silo 60/40 (earn-heavy)...", flush=True)
silos_60_40 = [
    {"signal_fn": make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                           industry_map=industry_map, min_peers=min_peers),
     "weight": 0.60, "name": "fundamental"},
    {"signal_fn": make_twin_star_signal_fn(top_n=25, bottom_n=12,
                                            industry_map=industry_map, min_peers=min_peers),
     "weight": 0.40, "name": "quant"},
]
r = run_experiment(data, silos_60_40, "multi-silo/60-40", dead_zone=0.015, is_multi_silo=True,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# Multi-Silo: 70/30 earnings-heavy
print("  [6/6] multi-silo 70/30 (earn-heavy)...", flush=True)
silos_70_30 = [
    {"signal_fn": make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                           industry_map=industry_map, min_peers=min_peers),
     "weight": 0.70, "name": "fundamental"},
    {"signal_fn": make_twin_star_signal_fn(top_n=25, bottom_n=12,
                                            industry_map=industry_map, min_peers=min_peers),
     "weight": 0.30, "name": "quant"},
]
r = run_experiment(data, silos_70_30, "multi-silo/70-30", dead_zone=0.015, is_multi_silo=True,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("PHASE 16 RESULTS: Multi-Silo vs Single-Stream")
print(f"{'=' * 80}\n")

df = pd.DataFrame(results)
df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

header = f"{'#':<3} {'Label':<30} {'Sharpe':>8} {'Std':>8} {'MaxDD':>8} {'Return':>10} {'Trades':>8}"
print(header)
print("-" * len(header))

for i, row in df.iterrows():
    sharpe = row.get("sharpe_ratio", 0)
    std = row.get("sharpe_std", 0)
    mdd = row.get("max_drawdown", 0)
    ret = row.get("total_return", 0)
    trades = row.get("trade_count", 0)
    label = row.get("label", "")

    marker = ""
    if sharpe >= 1.0 and std < 1.5:
        marker = " ***"
    elif sharpe >= 1.0:
        marker = " *"
    elif sharpe >= 0.95 and std < 1.5:
        marker = " **"

    print(f"{i+1:<3} {label:<30} {sharpe:>8.3f} {std:>8.3f} {mdd:>7.1%} {ret:>9.1%} {trades:>8.0f}{marker}")

print(f"\n{'=' * 80}")
print("TARGETS: Sharpe > 1.0, Std < 1.5 (down from 1.8)")
print("Baseline: twin-star Sharpe=0.818, Std=1.869")
print(f"{'=' * 80}")
