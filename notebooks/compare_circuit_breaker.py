"""Compare drawdown circuit breaker impact on walk-forward backtest.

Baseline: 50% gtja_momentum + 50% reversed_gtja_vwap (定版配置)
Test:     Same strategy + DrawdownCircuitBreaker

Output: per-period and aggregate metrics comparison.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.walk_forward import walk_forward_backtest
from config.loader import load_config
from data import validate_ohlcv
from data.fetcher import fetch_daily_batch
from data.filters import detect_limit_price, detect_suspension
from data.universe import resolve_universe
from portfolio.circuit_breaker import DrawdownCircuitBreaker
from strategies.combiner import WeightedVoteCombiner
from strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def make_combo_signal_fn():
    """Create signal_fn for 50% momentum + 50% reversed_vwap combo."""
    mom = get_strategy("gtja_momentum", rebalance=10, top_n=5, bottom_n=3)
    vwap = get_strategy("reversed_gtja_vwap", rebalance=20, top_n=5, bottom_n=3)
    combiner = WeightedVoteCombiner([(mom, 0.5), (vwap, 0.5)], threshold=0.0)

    def signal_fn(train_data, test_data):
        return combiner.combine(test_data)

    return signal_fn


def run_experiment(data, signal_fn, label, circuit_breaker=None):
    """Run walk-forward backtest and return per-period + summary metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=12, test_months=3,
        stop_loss=-0.15,
        circuit_breaker=circuit_breaker,
    )
    elapsed = time.time() - t0

    pp = result["per_period"]
    ov = result["overall"]

    if pp.empty:
        return {"label": label, "periods": 0, "elapsed": elapsed}, pp

    summary = {
        "label": label,
        "periods": len(pp),
        "total_return": ov["total_return"],
        "annual_return": ov["annual_return"],
        "sharpe_ratio": ov["sharpe_ratio"],
        "max_drawdown": ov["max_drawdown"],
        "win_rate": pp["win_rate"].mean(),
        "trade_count": pp["trade_count"].sum(),
        "cumulative": ov["total_return"],
        "elapsed": elapsed,
    }
    return summary, pp


# ── Load data ─────────────────────────────────────────────────────────────
print("=" * 70)
print("Drawdown Circuit Breaker Comparison")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "default.yaml")

print("\n[1/3] Loading CSI 300 data...", flush=True)
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

# ── Run experiments ────────────────────────────────────────────────────────
print("\n[2/3] Running walk-forward backtests...", flush=True)
signal_fn = make_combo_signal_fn()

# Baseline: no circuit breaker
print("  Baseline (no circuit breaker)...", flush=True)
summary_base, detail_base = run_experiment(data, signal_fn, "Baseline")

# Circuit breaker: threshold=-0.10 (conservative)
print("  Circuit Breaker (threshold=-0.10)...", flush=True)
cb_conservative = DrawdownCircuitBreaker(
    threshold=-0.10, recovery_threshold=-0.03, min_exposure=0.1,
)
summary_cb1, detail_cb1 = run_experiment(
    data, signal_fn, "CB threshold=-0.10", circuit_breaker=cb_conservative,
)

# Circuit breaker: threshold=-0.15 (aggressive)
print("  Circuit Breaker (threshold=-0.15)...", flush=True)
cb_aggressive = DrawdownCircuitBreaker(
    threshold=-0.15, recovery_threshold=-0.05, min_exposure=0.1,
)
summary_cb2, detail_cb2 = run_experiment(
    data, signal_fn, "CB threshold=-0.15", circuit_breaker=cb_aggressive,
)

# Circuit breaker: threshold=-0.08 (very aggressive)
print("  Circuit Breaker (threshold=-0.08)...", flush=True)
cb_very_agg = DrawdownCircuitBreaker(
    threshold=-0.08, recovery_threshold=-0.02, min_exposure=0.05,
)
summary_cb3, detail_cb3 = run_experiment(
    data, signal_fn, "CB threshold=-0.08", circuit_breaker=cb_very_agg,
)

# ── Summary table ──────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Summary")
print(f"{'=' * 70}\n")

summaries = [summary_base, summary_cb1, summary_cb2, summary_cb3]
df = pd.DataFrame(summaries)

fmt_cols = {
    "total_return": ".1%",
    "annual_return": ".2%",
    "sharpe_ratio": ".2f",
    "max_drawdown": ".1%",
    "win_rate": ".1%",
    "trade_count": ".0f",
    "cumulative": ".1%",
    "elapsed": ".1f",
}

header = f"{'Label':<25}"
for col in fmt_cols:
    header += f" {col:>14}"
print(header)
print("-" * len(header))

for _, row in df.iterrows():
    line = f"{row['label']:<25}"
    for col, fmt in fmt_cols.items():
        if col in row:
            line += f" {row[col]:>14{fmt}}"
        else:
            line += f" {'N/A':>14}"
    print(line)

# ── Per-period comparison ──────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Per-Period Comparison (Baseline vs CB threshold=-0.10)")
print(f"{'=' * 70}\n")

if not detail_base.empty and not detail_cb1.empty:
    comp = pd.DataFrame({
        "period": detail_base["period"],
        "baseline_return": detail_base["total_return"],
        "cb_return": detail_cb1["total_return"],
        "baseline_dd": detail_base["max_drawdown"],
        "cb_dd": detail_cb1["max_drawdown"],
    })

    comp["diff"] = comp["cb_return"] - comp["baseline_return"]

    print(f"{'Period':>6} {'Base Ret':>10} {'CB Ret':>10} {'Diff':>10} {'Base DD':>10} {'CB DD':>10}")
    print("-" * 58)
    for _, r in comp.iterrows():
        print(
            f"{int(r['period']):>6} "
            f"{r['baseline_return']:>10.1%} "
            f"{r['cb_return']:>10.1%} "
            f"{r['diff']:>10.1%} "
            f"{r['baseline_dd']:>10.1%} "
            f"{r['cb_dd']:>10.1%}"
        )

    # Count wins
    wins = (comp["diff"] > 0).sum()
    losses = (comp["diff"] < 0).sum()
    ties = (comp["diff"] == 0).sum()
    print(f"\nCB wins: {wins}, losses: {losses}, ties: {ties}")

print(f"\n{'=' * 70}")
print("Done.")
