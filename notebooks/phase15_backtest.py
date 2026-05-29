"""Phase 15 backtest: triple-star combiner (twin-star + earnings surprise).

Compares twin-star baseline vs triple-star with fundamental earnings factors.
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


def make_signal_fn(strategies_weights, threshold=0.0, industry_map=None, min_peers=3):
    """Create signal_fn for N-star combiner with configurable params."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        strats = []
        for name, weight, top_n, bottom_n in strategies_weights:
            s = get_strategy(name, rebalance=20, top_n=top_n, bottom_n=bottom_n, **extra)
            strats.append((s, weight))
        combiner = WeightedVoteCombiner(strats, threshold=threshold)
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
print("Phase 15 Backtest: Triple-Star vs Twin-Star")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "production.yaml")

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"

# Step 1: Fetch OHLCV
print(f"\n[1/4] Loading OHLCV data ({START_DATE} to {END_DATE})...", flush=True)
codes = resolve_universe(cfg["universe"])
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

# Step 2: Fetch earnings data (per-stock, with caching)
print("\n[2/4] Fetching earnings data for all stocks...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0.8, progress=True)
print(f"  {len(earnings_raw)} events fetched ({time.time()-t0:.1f}s)")

# Step 3: Build earnings panel and merge
print("\n[3/4] Building earnings panel (PIT + Z-Score)...", flush=True)
t0 = time.time()
trade_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
print(f"  Panel: {len(earnings_panel)} rows ({time.time()-t0:.1f}s)")

# Merge into data
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  Merged. earnings_surprise non-zero: {(data['earnings_surprise'] != 0).sum()}")

# Step 4: Build industry map
print("\n[4/4] Building industry map...", flush=True)
industry_cfg = build_industry_map(cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped, min_peers={min_peers}")

# ── Run experiments ────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Running experiments...")
print(f"{'=' * 70}\n")

TOP_N = 5
BOTTOM_N = 3

experiments = [
    # Twin-star baseline (original production config)
    ("twin-star/0.52", [
        ("reversed_gtja_vwap", 0.52, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.48, TOP_N, BOTTOM_N),
    ], 0.5, 0.01),

    # Triple-star: equal weight
    ("triple-equal", [
        ("reversed_gtja_vwap", 0.33, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.33, TOP_N, BOTTOM_N),
        ("gtja_earnings_surprise", 0.34, TOP_N, BOTTOM_N),
    ], 0.5, 0.01),

    # Triple-star: vwap-heavy
    ("triple-vwap-heavy", [
        ("reversed_gtja_vwap", 0.40, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.35, TOP_N, BOTTOM_N),
        ("gtja_earnings_surprise", 0.25, TOP_N, BOTTOM_N),
    ], 0.5, 0.01),

    # Triple-star: earnings-heavy
    ("triple-earn-heavy", [
        ("reversed_gtja_vwap", 0.30, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.30, TOP_N, BOTTOM_N),
        ("gtja_earnings_surprise", 0.40, TOP_N, BOTTOM_N),
    ], 0.5, 0.01),

    # Triple-star with threshold sweep
    ("triple-t0.3", [
        ("reversed_gtja_vwap", 0.35, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.35, TOP_N, BOTTOM_N),
        ("gtja_earnings_surprise", 0.30, TOP_N, BOTTOM_N),
    ], 0.3, 0.01),

    ("triple-t0.7", [
        ("reversed_gtja_vwap", 0.35, TOP_N, BOTTOM_N),
        ("gtja_volatility", 0.35, TOP_N, BOTTOM_N),
        ("gtja_earnings_surprise", 0.30, TOP_N, BOTTOM_N),
    ], 0.7, 0.01),

    # Earnings-only baseline (standalone)
    ("earnings-only", [
        ("gtja_earnings_surprise", 1.0, TOP_N, BOTTOM_N),
    ], 0.0, 0.01),
]

results = []
for i, (label, strats_w, thresh, dz) in enumerate(experiments, 1):
    fn = make_signal_fn(strats_w, threshold=thresh,
                        industry_map=industry_map, min_peers=min_peers)
    print(f"  [{i}/{len(experiments)}] {label} (threshold={thresh})...", flush=True)
    r = run_experiment(data, fn, label, dead_zone=dz)
    results.append(r)
    print(f"    Sharpe={r.get('sharpe_ratio', 0):.3f}  MaxDD={r.get('max_drawdown', 0):.1%}  "
          f"Return={r.get('total_return', 0):.1%}  Trades={r.get('trade_count', 0)}")

# ── Summary table ─────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Phase 15 Results: Triple-Star vs Twin-Star")
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

# ── Best config ───────────────────────────────────────────────────────
if "sharpe_ratio" in df.columns and df["sharpe_ratio"].notna().any():
    best_idx = df["sharpe_ratio"].idxmax()
    best = df.loc[best_idx]
    print(f"\n{'=' * 70}")
    print(f"Best: {best['label']} (Sharpe={best['sharpe_ratio']:.3f})")
    print(f"{'=' * 70}")

print(f"\n{'=' * 70}")
print("Done.")
