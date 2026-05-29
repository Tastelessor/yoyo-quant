"""Phase 14 backtest: twin-star combiner + neutralization + concentration + dead-zone.

Tests the full parameter matrix: top_n × threshold × dead_zone.
All experiments use neutralization (the proven +51% Sharpe boost).
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
from src.data.fetcher import fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.strategies.combiner import WeightedVoteCombiner
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_twin_star_signal_fn(top_n=5, bottom_n=3, threshold=0.0,
                              industry_map=None, min_peers=3):
    """Create signal_fn for twin-star combiner with configurable params."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        vwap = get_strategy(
            "reversed_gtja_vwap", rebalance=20,
            top_n=top_n, bottom_n=bottom_n, **extra,
        )
        vol = get_strategy(
            "gtja_volatility", rebalance=20,
            top_n=top_n, bottom_n=bottom_n, **extra,
        )
        combiner = WeightedVoteCombiner(
            [(vwap, 0.52), (vol, 0.48)], threshold=threshold,
        )
        return combiner.combine(test_data)
    return signal_fn


def run_experiment(data, signal_fn, label, dead_zone=0.0):
    """Run walk-forward backtest and return summary metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=12, test_months=3,
        dead_zone=dead_zone,
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
        "trade_count": pp["trade_count"].sum(),
        "elapsed": elapsed,
    }


# ── Load data ─────────────────────────────────────────────────────────
print("=" * 70)
print("Phase 14 Backtest: Full Parameter Matrix")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "default.yaml")

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"

print(f"\n[1/3] Loading data ({START_DATE} to {END_DATE})...", flush=True)
codes = resolve_universe(cfg["universe"])
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

# Build industry map
print("\n[2/3] Building industry map...", flush=True)
industry_cfg = build_industry_map(cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped, min_peers={min_peers}")

# ── Run experiments ────────────────────────────────────────────────────
print("\n[3/3] Running experiments...", flush=True)

# All experiments use neutralization (proven boost)
experiments = [
    # (label, top_n, bottom_n, threshold, dead_zone)
    ("N5/t0.0/dz0", 5, 3, 0.0, 0.0),
    ("N5/t0.0/dz01", 5, 3, 0.0, 0.01),
    ("N5/t0.3/dz0", 5, 3, 0.3, 0.0),
    ("N5/t0.3/dz01", 5, 3, 0.3, 0.01),
    ("N5/t0.5/dz0", 5, 3, 0.5, 0.0),
    ("N5/t0.5/dz01", 5, 3, 0.5, 0.01),
    ("N10/t0.0/dz0", 10, 5, 0.0, 0.0),
    ("N10/t0.0/dz01", 10, 5, 0.0, 0.01),
    ("N10/t0.5/dz0", 10, 5, 0.5, 0.0),
    ("N10/t0.5/dz01", 10, 5, 0.5, 0.01),
]

results = []
for i, (label, top_n, bottom_n, thresh, dz) in enumerate(experiments, 1):
    fn = make_twin_star_signal_fn(
        top_n=top_n, bottom_n=bottom_n, threshold=thresh,
        industry_map=industry_map, min_peers=min_peers,
    )
    print(f"  [{i}/{len(experiments)}] {label}...", flush=True)
    r = run_experiment(data, fn, label, dead_zone=dz)
    results.append(r)
    print(f"    Sharpe={r['sharpe_ratio']:.3f}  MaxDD={r['max_drawdown']:.1%}  "
          f"Return={r['total_return']:.1%}  Trades={r['trade_count']}")

# ── Summary table ─────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Results Summary (all with neutralization)")
print(f"{'=' * 70}\n")

df = pd.DataFrame(results)

fmt_cols = {
    "total_return": ".1%",
    "annual_return": ".2%",
    "sharpe_ratio": ".3f",
    "max_drawdown": ".1%",
    "trade_count": ".0f",
    "elapsed": ".1f",
}

header = f"{'Label':<20}"
for col in fmt_cols:
    header += f" {col:>14}"
print(header)
print("-" * len(header))

for _, row in df.iterrows():
    line = f"{row['label']:<20}"
    for col, fmt in fmt_cols.items():
        if col in row and pd.notna(row[col]):
            line += f" {row[col]:>14{fmt}}"
        else:
            line += f" {'N/A':>14}"
    print(line)

# ── Best config detail ────────────────────────────────────────────────
best_idx = df["sharpe_ratio"].idxmax()
best = df.loc[best_idx]
best_exp = experiments[best_idx]
print(f"\n{'=' * 70}")
print(f"Best: {best['label']} (Sharpe={best['sharpe_ratio']:.3f})")
print(f"  top_n={best_exp[1]}, bottom_n={best_exp[2]}, threshold={best_exp[3]}, dead_zone={best_exp[4]}")
print(f"{'=' * 70}")

print(f"\n{'=' * 70}")
print("Done.")
