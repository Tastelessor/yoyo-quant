"""Phase 15 production grid search: weights × threshold × dead_zone.

Searches for Sharpe > 1.0 with cross-period std < 1.2.
top_n locked at 10-15 range.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.walk_forward import walk_forward_backtest
from src.config.loader import build_industry_map, load_config
from src.data import validate_ohlcv
from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.fetcher import fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.strategies.combiner import WeightedVoteCombiner
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_signal_fn(strategies_weights, threshold, industry_map, min_peers):
    """Create signal_fn for N-star combiner."""
    def signal_fn(train_data, test_data):
        extra = {"industry_map": industry_map, "min_peers": min_peers}
        strats = []
        for name, weight, top_n, bottom_n in strategies_weights:
            s = get_strategy(name, rebalance=20, top_n=top_n, bottom_n=bottom_n, **extra)
            strats.append((s, weight))
        combiner = WeightedVoteCombiner(strats, threshold=threshold)
        return combiner.combine(test_data)
    return signal_fn


def run_experiment(data, signal_fn, label, dead_zone):
    """Run walk-forward and compute Sharpe + cross-period std."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=12, test_months=3,
        dead_zone=dead_zone,
    )
    elapsed = time.time() - t0

    if result.empty or len(result) < 2:
        return {"label": label, "periods": 0, "elapsed": elapsed}

    avg_sharpe = result["sharpe_ratio"].mean()
    std_sharpe = result["sharpe_ratio"].std()
    avg_return = result["annual_return"].mean()
    avg_maxdd = result["max_drawdown"].mean()
    total_trades = result["trade_count"].sum()

    compound = 1.0
    for r in result["total_return"]:
        compound *= (1 + r)
    total_return = compound - 1

    # Fix overflow
    if abs(avg_sharpe) > 100:
        avg_sharpe = 0.0

    return {
        "label": label,
        "periods": len(result),
        "total_return": total_return,
        "annual_return": avg_return,
        "sharpe_ratio": avg_sharpe,
        "sharpe_std": std_sharpe,
        "max_drawdown": avg_maxdd,
        "trade_count": total_trades,
        "elapsed": elapsed,
    }


# ── Load data ─────────────────────────────────────────────────────────
print("=" * 80)
print("Phase 15 Production Grid Search")
print("Target: Sharpe > 1.0, cross-period std < 1.2")
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
trade_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
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

# ── Grid search ───────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("[4/4] Running grid search...")
print(f"{'=' * 80}\n")

TOP_N_GRID = [10, 15]
BOTTOM_N_GRID = [5, 8]  # bottom_n = top_n // 2

WEIGHT_GRID = {
    "w35_35_30": [("reversed_gtja_vwap", 0.35), ("gtja_volatility", 0.35), ("gtja_earnings_surprise", 0.30)],
    "w40_40_20": [("reversed_gtja_vwap", 0.40), ("gtja_volatility", 0.40), ("gtja_earnings_surprise", 0.20)],
}

THRESHOLD_GRID = [0.4, 0.5, 0.6]
DEAD_ZONE = 0.015

# Also include earnings-only baselines
EXTRA_CONFIGS = [
    ("earn-only/N10", [("gtja_earnings_surprise", 1.0, 10, 5)], 0.0),
    ("earn-only/N12", [("gtja_earnings_surprise", 1.0, 12, 6)], 0.0),
    ("earn-only/N15", [("gtja_earnings_surprise", 1.0, 15, 8)], 0.0),
    ("earn-only/N10/rb15", [("gtja_earnings_surprise", 1.0, 10, 5)], 0.0),  # special: rb=15
]

results = []

# Run earnings-only baselines (with rebalance sweep)
for label, strats_w, thresh in EXTRA_CONFIGS:
    for rb in [15, 20]:
        full_label = f"{label}/rb{rb}" if "rb" not in label else label
        if "rb15" in label and rb == 20:
            continue
        if "rb15" not in label and rb == 15:
            full_label = f"{label}/rb{rb}"

        def signal_fn(train, test, sw=strats_w, t=thresh, r=rb):
            extra = {"industry_map": industry_map, "min_peers": min_peers}
            strats = [(get_strategy(n, rebalance=r, top_n=tn, bottom_n=bn, **extra), w) for n, w, tn, bn in sw]
            return WeightedVoteCombiner(strats, threshold=t).combine(test)

        print(f"  {full_label}...", end="", flush=True)
        r = run_experiment(data, signal_fn, full_label, DEAD_ZONE)
        results.append(r)
        sharpe = r.get("sharpe_ratio", 0)
        std = r.get("sharpe_std", 0)
        ret = r.get("total_return", 0)
        mdd = r.get("max_drawdown", 0)
        trades = r.get("trade_count", 0)
        print(f"  Sharpe={sharpe:.3f}  Std={std:.3f}  MaxDD={mdd:.1%}  Return={ret:.1%}  Trades={trades}")

# Run triple-star grid
for w_name, w_list in WEIGHT_GRID.items():
    for top_n, bottom_n in zip(TOP_N_GRID, BOTTOM_N_GRID):
        for thresh in THRESHOLD_GRID:
            strats_w = [(name, w, top_n, bottom_n) for name, w in w_list]
            label = f"triple/{w_name}/N{top_n}/t{thresh}"

            def signal_fn(train, test, sw=strats_w, t=thresh):
                extra = {"industry_map": industry_map, "min_peers": min_peers}
                strats = [(get_strategy(n, rebalance=20, top_n=tn, bottom_n=bn, **extra), w) for n, w, tn, bn in sw]
                return WeightedVoteCombiner(strats, threshold=t).combine(test)

            print(f"  {label}...", end="", flush=True)
            r = run_experiment(data, signal_fn, label, DEAD_ZONE)
            results.append(r)
            sharpe = r.get("sharpe_ratio", 0)
            std = r.get("sharpe_std", 0)
            ret = r.get("total_return", 0)
            mdd = r.get("max_drawdown", 0)
            trades = r.get("trade_count", 0)
            print(f"  Sharpe={sharpe:.3f}  Std={std:.3f}  MaxDD={mdd:.1%}  Return={ret:.1%}  Trades={trades}")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("RESULTS SUMMARY")
print(f"{'=' * 80}\n")

df = pd.DataFrame(results)

# Sort by Sharpe
df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

header = f"{'#':<3} {'Label':<35} {'Sharpe':>8} {'Std':>8} {'MaxDD':>8} {'Return':>10} {'Trades':>8}"
print(header)
print("-" * len(header))

for i, row in df.iterrows():
    sharpe = row.get("sharpe_ratio", 0)
    std = row.get("sharpe_std", 0)
    mdd = row.get("max_drawdown", 0)
    ret = row.get("total_return", 0)
    trades = row.get("trade_count", 0)
    label = row.get("label", "")

    # Highlight targets
    marker = ""
    if sharpe >= 1.0 and std < 1.2:
        marker = " ***"
    elif sharpe >= 1.0:
        marker = " *"
    elif sharpe >= 0.95 and std < 1.2:
        marker = " **"

    print(f"{i+1:<3} {label:<35} {sharpe:>8.3f} {std:>8.3f} {mdd:>7.1%} {ret:>9.1%} {trades:>8.0f}{marker}")

# ── Target analysis ───────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("TARGET ANALYSIS: Sharpe > 1.0 AND Std < 1.2")
print(f"{'=' * 80}\n")

hits = df[(df["sharpe_ratio"] >= 1.0) & (df["sharpe_std"] < 1.2)]
if len(hits) > 0:
    print(f"  Found {len(hits)} configurations meeting both targets!")
    for _, row in hits.iterrows():
        print(f"  -> {row['label']}: Sharpe={row['sharpe_ratio']:.3f}, Std={row['sharpe_std']:.3f}")
else:
    print("  No configuration meets both targets simultaneously.")
    print("\n  Closest to Sharpe > 1.0:")
    near_1 = df[df["sharpe_ratio"] >= 0.95].head(3)
    for _, row in near_1.iterrows():
        print(f"    {row['label']}: Sharpe={row['sharpe_ratio']:.3f}, Std={row['sharpe_std']:.3f}")

    print("\n  Lowest cross-period std:")
    low_std = df.nsmallest(3, "sharpe_std")
    for _, row in low_std.iterrows():
        print(f"    {row['label']}: Sharpe={row['sharpe_ratio']:.3f}, Std={row['sharpe_std']:.3f}")

print(f"\n{'=' * 80}")
print("Baseline: twin-star Sharpe=0.818, Std=1.869")
print(f"{'=' * 80}")
