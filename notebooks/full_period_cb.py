"""Full-period continuous backtest with DrawdownCircuitBreaker.

This runs BacktestEngine.run() ONCE over the full 3-year period,
so the equity curve is continuous and the CB operates on a proper
high-water mark (not per-period resets).

Baseline: 50% gtja_momentum + 50% reversed_gtja_vwap (定版配置)
Test:     Same strategy + DrawdownCircuitBreaker (various thresholds)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import BacktestEngine, TradingCost
from src.config.loader import load_config
from src.data import validate_ohlcv
from src.data.fetcher import fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.portfolio.allocator import equal_weight
from src.portfolio.circuit_breaker import DrawdownCircuitBreaker
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable
from src.strategies.combiner import WeightedVoteCombiner
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def generate_full_period_signals(data, rebalance=10):
    """Generate signals for the full period using 50/50 combo."""
    mom = get_strategy("gtja_momentum", rebalance=rebalance, top_n=5, bottom_n=3)
    vwap = get_strategy("reversed_gtja_vwap", rebalance=20, top_n=5, bottom_n=3)
    combiner = WeightedVoteCombiner([(mom, 0.5), (vwap, 0.5)], threshold=0.0)
    signals = combiner.combine(data)
    return signals


def run_full_period(data, signals, label, capital=1_000_000, circuit_breaker=None):
    """Run single BacktestEngine over full period."""
    t0 = time.time()

    # Filter tradability
    signals = filter_tradable(data, signals)
    signals = enforce_t1(signals)

    # Allocate positions
    prices = data[["date", "code", "close"]].drop_duplicates()
    positions = equal_weight(signals, prices, capital=capital)

    # Position limit
    positions = apply_position_limit(positions, max_weight=0.3)

    # Run engine
    tc = TradingCost(
        commission=0.0001, stamp_tax=0.0005,
        transfer_fee=0.00001, slippage_ticks=1,
    )
    engine = BacktestEngine(
        capital=capital, stop_loss=-0.15, take_profit=0.05,
        trading_cost=tc, circuit_breaker=circuit_breaker,
    )
    result = engine.run(positions, prices, market_data=data)
    elapsed = time.time() - t0

    eq = result["equity_curve"]
    metrics = result["metrics"]
    trades = result["trades"]

    # Compute additional metrics
    if len(eq) > 1:
        eq["returns"] = eq["equity"].pct_change().fillna(0.0)
        daily_ret = eq["returns"]
        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0.0

        # Max drawdown from equity curve
        peak = eq["equity"].cummax()
        dd = (eq["equity"] - peak) / peak
        max_dd = dd.min()

        # Annualized return
        n_days = len(eq)
        total_ret = (eq["equity"].iloc[-1] / capital) - 1
        annual_ret = (1 + total_ret) ** (252 / max(n_days, 1)) - 1
    else:
        sharpe = max_dd = total_ret = annual_ret = 0.0

    cb_trades = trades[trades["action"] == "cb_compress"] if not trades.empty else pd.DataFrame()

    return {
        "label": label,
        "total_return": total_ret,
        "annual_return": annual_ret,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "trade_count": len(trades),
        "cb_trades": len(cb_trades),
        "final_equity": eq["equity"].iloc[-1] if len(eq) > 0 else capital,
        "elapsed": elapsed,
    }, eq, trades


# ── Load data ─────────────────────────────────────────────────────────────
print("=" * 70)
print("Full-Period Continuous Backtest: DrawdownCircuitBreaker")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "default.yaml")

print("\n[1/3] Loading data...", flush=True)
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

# ── Generate signals ──────────────────────────────────────────────────────
print("\n[2/3] Generating signals...", flush=True)
t0 = time.time()
signals = generate_full_period_signals(data)
n_signals = len(signals)
n_buy = (signals["signal"] == 1).sum()
print(f"  {n_signals} total signals, {n_buy} buy ({time.time()-t0:.1f}s)")

# ── Run backtests ──────────────────────────────────────────────────────────
print("\n[3/3] Running full-period backtests...", flush=True)

results = []

# Baseline
print("  Baseline (no CB)...", flush=True)
r_base, eq_base, _ = run_full_period(data, signals, "Baseline")
results.append(r_base)

# CB with dead-zone + fast recovery
configs = [
    # (threshold, recovery, label, dead_zone, fast_momentum, fast_window)
    (-0.10, -0.03, "CB-10% DZ5 FR5", 0.05, 0.05, 3),
    (-0.15, -0.05, "CB-15% DZ5 FR5", 0.05, 0.05, 3),
    (-0.15, -0.05, "CB-15% DZ3 FR5", 0.03, 0.05, 3),
    (-0.15, -0.05, "CB-15% DZ5 FR3", 0.05, 0.03, 3),
    (-0.15, -0.05, "CB-15% DZ5 FR8", 0.05, 0.08, 3),
    (-0.15, -0.05, "CB-15% DZ5 FR5w5", 0.05, 0.05, 5),
    (-0.20, -0.07, "CB-20% DZ5 FR5", 0.05, 0.05, 3),
    (-0.25, -0.10, "CB-25% DZ5 FR5", 0.05, 0.05, 3),
    (-0.30, -0.12, "CB-30% DZ5 FR5", 0.05, 0.05, 3),
    (-0.30, -0.10, "CB-30% DZ5 FR3", 0.05, 0.03, 3),
    (-0.35, -0.15, "CB-35% DZ5 FR5", 0.05, 0.05, 3),
    (-0.40, -0.18, "CB-40% DZ5 FR5", 0.05, 0.05, 3),
    (-0.45, -0.20, "CB-45% DZ5 FR5", 0.05, 0.05, 3),
    (-0.50, -0.22, "CB-50% DZ5 FR5", 0.05, 0.05, 3),
]

for threshold, recovery, label, dz, fr_mom, fr_win in configs:
    print(f"  {label}...", flush=True)
    cb = DrawdownCircuitBreaker(
        threshold=threshold, recovery_threshold=recovery, min_exposure=0.1,
        dead_zone=dz, fast_recovery_momentum=fr_mom, fast_recovery_window=fr_win,
    )
    r_cb, eq_cb, trades_cb = run_full_period(
        data, signals, label, circuit_breaker=cb,
    )
    results.append(r_cb)

# ── Summary table ──────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Results")
print(f"{'=' * 70}\n")

df = pd.DataFrame(results)

fmt_cols = {
    "total_return": ".1%",
    "annual_return": ".2%",
    "sharpe_ratio": ".3f",
    "max_drawdown": ".1%",
    "trade_count": ".0f",
    "cb_trades": ".0f",
    "final_equity": ",.0f",
    "elapsed": ".1f",
}

header = f"{'Label':<15}"
for col in fmt_cols:
    header += f" {col:>14}"
print(header)
print("-" * len(header))

for _, row in df.iterrows():
    line = f"{row['label']:<15}"
    for col, fmt in fmt_cols.items():
        if col in row:
            line += f" {row[col]:>14{fmt}}"
        else:
            line += f" {'N/A':>14}"
    print(line)

# ── Equity curve analysis ──────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Equity Curve Analysis")
print(f"{'=' * 70}\n")

# Show key drawdown periods
peak = eq_base["equity"].cummax()
dd = (eq_base["equity"] - peak) / peak
worst_dd_idx = dd.idxmin()
worst_dd_date = eq_base.loc[worst_dd_idx, "date"]
worst_dd_val = dd.min()

print(f"Baseline worst drawdown: {worst_dd_val:.1%} on {worst_dd_date.strftime('%Y-%m-%d')}")

# Find the peak before the worst drawdown
peak_idx = eq_base.loc[:worst_dd_idx, "equity"].idxmax()
peak_date = eq_base.loc[peak_idx, "date"]
print(f"  From peak on {peak_date.strftime('%Y-%m-%d')} ({eq_base.loc[peak_idx, 'equity']:,.0f})")
print(f"  To trough on {worst_dd_date.strftime('%Y-%m-%d')} ({eq_base.loc[worst_dd_idx, 'equity']:,.0f})")

# Show monthly returns (Baseline vs best CB config)
print("\nMonthly returns (Baseline vs CB-15% DZ5 FR5):")
eq_base_copy = eq_base.copy()
eq_base_copy["month"] = eq_base_copy["date"].dt.to_period("M")
monthly_base = eq_base_copy.groupby("month")["equity"].agg(["first", "last"])
monthly_base["return"] = (monthly_base["last"] / monthly_base["first"]) - 1

# Get CB-15% DZ5 FR5 equity for comparison
cb_best = DrawdownCircuitBreaker(
    threshold=-0.15, recovery_threshold=-0.05, min_exposure=0.1,
    dead_zone=0.05, fast_recovery_momentum=0.05, fast_recovery_window=3,
)
_, eq_cb_best, _ = run_full_period(data, signals, "CB-15% DZ5 FR5", circuit_breaker=cb_best)
eq_cb_best_copy = eq_cb_best.copy()
eq_cb_best_copy["month"] = eq_cb_best_copy["date"].dt.to_period("M")
monthly_cb = eq_cb_best_copy.groupby("month")["equity"].agg(["first", "last"])
monthly_cb["return"] = (monthly_cb["last"] / monthly_cb["first"]) - 1

print(f"{'Month':<10} {'Base Ret':>10} {'CB Ret':>10} {'Diff':>10}")
print("-" * 42)
for month in monthly_base.index:
    base_r = monthly_base.loc[month, "return"]
    cb_r = monthly_cb.loc[month, "return"] if month in monthly_cb.index else 0.0
    diff = cb_r - base_r
    marker = " *" if abs(diff) > 0.02 else ""
    print(f"{str(month):<10} {base_r:>10.1%} {cb_r:>10.1%} {diff:>10.1%}{marker}")

print("\n* = |diff| > 2%")

print(f"\n{'=' * 70}")
print("Done.")
