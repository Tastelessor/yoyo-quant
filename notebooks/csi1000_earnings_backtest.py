"""CSI 1000 + Earnings Surprise backtest.

Compare earnings-only and twin-star strategies on CSI 1000 universe
with industry neutralization, using corrected overall metrics.
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
from src.data.fetcher import fetch_daily_batch, fetch_index_constituents
from src.data.filters import detect_limit_price, detect_suspension
from src.strategies.combiner import WeightedVoteCombiner
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"


def make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                             industry_map=None, min_peers=3):
    """Earnings-only strategy."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        s = get_strategy("gtja_earnings_surprise",
                         rebalance=rebalance, top_n=top_n, bottom_n=bottom_n, **extra)
        return s.generate_signal(test_data)
    return signal_fn


def make_twin_star_signal_fn(top_n=25, bottom_n=12, industry_map=None, min_peers=3):
    """Twin-star quant strategy (reversed_vwap + volatility)."""
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


def run_experiment(data, signal_fn, label, dead_zone, **wf_kwargs):
    """Run walk-forward and return metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=12, test_months=3,
        dead_zone=dead_zone,
        **wf_kwargs,
    )
    elapsed = time.time() - t0

    pp = result["per_period"]
    ov = result["overall"]

    if pp.empty or len(pp) < 2:
        return {"label": label, "periods": 0, "elapsed": elapsed}

    return {
        "label": label,
        "periods": len(pp),
        "total_return": ov["total_return"],
        "annual_return": ov["annual_return"],
        "sharpe_ratio": ov["sharpe_ratio"],
        "sharpe_std": ov["per_period_sharpe_std"],
        "max_drawdown": ov["max_drawdown"],
        "trade_count": int(pp["trade_count"].sum()),
        "elapsed": elapsed,
    }


# ── Load CSI 1000 universe ────────────────────────────────────────────
print("=" * 80)
print("CSI 1000 + Earnings Surprise Backtest")
print("=" * 80)

print(f"\n[1/4] Fetching CSI 1000 constituents...", flush=True)
codes = fetch_index_constituents("000852.SH", date="2026-05-23")
print(f"  {len(codes)} stocks")

print(f"\n[2/4] Loading OHLCV ({START_DATE} to {END_DATE})...", flush=True)
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=False)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

print("\n[3/4] Loading earnings data (cached)...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0, progress=False)
trade_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  {len(earnings_raw)} events, {time.time()-t0:.1f}s")

# Build industry map
print("\n[4/4] Building industry map...", flush=True)
from src.config.loader import load_config as _lc
_cfg = _lc(PROJECT_ROOT / "configs" / "production.yaml")
industry_cfg = build_industry_map(_cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped")

# ── Run experiments ────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("Running experiments...")
print(f"{'=' * 80}\n")

results = []

# 1: earnings-only N=10 rb=15
print("  [1/4] earn-only/N10/rb15 (CSI 1000)...", flush=True)
fn_earn = make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                   industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_earn, "earn/N10/rb15", dead_zone=0.015,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# 2: earnings-only N=15
print("  [2/4] earn-only/N15/rb15 (CSI 1000)...", flush=True)
fn_earn15 = make_earnings_signal_fn(top_n=15, bottom_n=8, rebalance=15,
                                     industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_earn15, "earn/N15/rb15", dead_zone=0.015,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# 3: earnings-only N=20 (more diversified for 1000-stock universe)
print("  [3/4] earn-only/N20/rb15 (CSI 1000)...", flush=True)
fn_earn20 = make_earnings_signal_fn(top_n=20, bottom_n=10, rebalance=15,
                                     industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_earn20, "earn/N20/rb15", dead_zone=0.015,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# 4: twin-star baseline
print("  [4/4] twin-star/N25 (CSI 1000)...", flush=True)
fn_ts = make_twin_star_signal_fn(top_n=25, bottom_n=12,
                                  industry_map=industry_map, min_peers=min_peers)
r = run_experiment(data, fn_ts, "twin-star/N25", dead_zone=0.015,
                   industry_map=industry_map)
results.append(r)
print(f"    Sharpe={r['sharpe_ratio']:.3f}  Std={r['sharpe_std']:.3f}  MaxDD={r['max_drawdown']:.1%}  Return={r['total_return']:.1%}")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("CSI 1000 RESULTS (corrected overall metrics)")
print(f"{'=' * 80}\n")

df = pd.DataFrame(results)
df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

header = f"{'#':<3} {'Label':<25} {'Sharpe':>8} {'Std':>8} {'MaxDD':>8} {'Return':>10} {'Trades':>8}"
print(header)
print("-" * len(header))

for i, row in df.iterrows():
    print(f"{i+1:<3} {row['label']:<25} {row['sharpe_ratio']:>8.3f} {row['sharpe_std']:>8.3f} {row['max_drawdown']:>7.1%} {row['total_return']:>9.1%} {row['trade_count']:>8.0f}")

print(f"\n{'=' * 80}")
print("Cross-market comparison (earn-only/N10/rb15):")
print("  CSI 300:  Sharpe=0.665  MaxDD=25.2%  Return=171%  (10y)")
print("  CSI 500:  Sharpe=0.930  MaxDD=14.4%  Return=37%   (3.4y)")
print("  CSI 1000: see above")
print(f"{'=' * 80}")
