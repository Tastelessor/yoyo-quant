"""Strategy Quality Diagnostic — four-dimensional assessment.

Runs earnings_surprise (CSI 500, N=10, rb=15) through:
1. IR (Information Ratio) — per-period consistency
2. Overfitting gap — continuous vs walk-forward Sharpe
3. Cost sensitivity — Sharpe elasticity across 5 cost tiers
4. Time stability — per-period Sharpe trend + half-period comparison

Outputs a decision table with pass/fail against live-trading thresholds.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import TradingCost
from src.backtest.walk_forward import walk_forward_backtest
from src.backtest.continuous import continuous_backtest
from src.config.loader import build_industry_map, load_config
from src.data import validate_ohlcv
from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.fetcher import fetch_daily_batch, fetch_index_constituents
from src.data.filters import detect_limit_price, detect_suspension
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "output"

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"

# ── Live-trading thresholds ────────────────────────────────────────────
THRESHOLDS = {
    "IR": (">", 0.5),
    "Cost Elasticity": ("<", 2.0),
    "Trend Slope": (">", -0.05),
    "WF-Continuous Gap": (">", -0.30),
}


def make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                             industry_map=None, min_peers=3):
    """Earnings-only strategy (walk-forward variant: train_data, test_data)."""
    def signal_fn(train_data, test_data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        s = get_strategy("gtja_earnings_surprise",
                         rebalance=rebalance, top_n=top_n, bottom_n=bottom_n, **extra)
        return s.generate_signal(test_data)
    return signal_fn


def make_continuous_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                               industry_map=None, min_peers=3):
    """Earnings-only strategy (continuous variant: data only)."""
    def signal_fn(data):
        extra = {}
        if industry_map is not None:
            extra = {"industry_map": industry_map, "min_peers": min_peers}
        s = get_strategy("gtja_earnings_surprise",
                         rebalance=rebalance, top_n=top_n, bottom_n=bottom_n, **extra)
        return s.generate_signal(data)
    return signal_fn


# ═══════════════════════════════════════════════════════════════════════
# Load data
# ═══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("Strategy Quality Diagnostic — earnings_surprise / CSI 500")
print("=" * 80)

print("\n[1/4] Fetching CSI 500 constituents...", flush=True)
codes = fetch_index_constituents("000905.SH", date="2026-05-23")
print(f"  {len(codes)} stocks")

print(f"\n[2/4] Loading OHLCV ({START_DATE} to {END_DATE})...", flush=True)
t0 = time.time()
data = fetch_daily_batch(codes, START_DATE, END_DATE, RAW_DIR, sleep_sec=0, progress=False)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time()-t0:.1f}s)")

print("\n[3/4] Loading earnings data...", flush=True)
t0 = time.time()
earnings_raw = fetch_earnings_history(codes, sleep_sec=0, progress=False)
trade_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
all_codes = sorted(data["code"].unique())
earnings_panel = build_earnings_panel(earnings_raw, trade_dates, all_codes)
data = data.merge(earnings_panel, on=["date", "code"], how="left")
data["earnings_surprise"] = data["earnings_surprise"].fillna(0.0)
data["earnings_acceleration"] = data["earnings_acceleration"].fillna(0.0)
print(f"  {len(earnings_raw)} events, {time.time()-t0:.1f}s")

print("\n[4/4] Building industry map...", flush=True)
_cfg = load_config(PROJECT_ROOT / "configs" / "production.yaml")
industry_cfg = build_industry_map(_cfg)
industry_map, min_peers = industry_cfg
print(f"  {len(industry_map)} stocks mapped")

# ═══════════════════════════════════════════════════════════════════════
# Diagnostic 1: Walk-forward baseline + IR
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("DIAGNOSTIC 1: Walk-Forward Baseline + IR")
print(f"{'=' * 80}\n")

fn_wf = make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                 industry_map=industry_map, min_peers=min_peers)

default_tc = TradingCost()  # commission=0.01%, slippage=1 tick

t0 = time.time()
wf_result = walk_forward_backtest(
    data, fn_wf,
    train_months=12, test_months=3,
    dead_zone=0.015,
    industry_map=industry_map,
    trading_cost=default_tc,
)
wf_elapsed = time.time() - t0

pp = wf_result["per_period"]
ov = wf_result["overall"]

wf_sharpe = ov["sharpe_ratio"]
wf_ir = ov["per_period_ir"]
pp_mean = ov["per_period_sharpe_mean"]
pp_std = ov["per_period_sharpe_std"]

print(f"  Overall Sharpe:   {wf_sharpe:.3f}")
print(f"  Per-pd Mean:      {pp_mean:.3f}")
print(f"  Per-pd Std:       {pp_std:.3f}")
print(f"  IR (mean/std):    {wf_ir:.3f}")
print(f"  Periods:          {len(pp)}")
print(f"  Elapsed:          {wf_elapsed:.1f}s")

print(f"\n  Per-period Sharpe breakdown:")
print(f"  {'Period':<25} {'Sharpe':>8} {'MaxDD':>8} {'MktRet':>8} {'Trades':>7} {'CostR':>7}")
print(f"  {'-'*64}")
for _, row in pp.iterrows():
    # Compute equal-weighted market return for this period
    period_data = data[
        (data["date"] >= row["test_start"]) & (data["date"] <= row["test_end"])
    ]
    if not period_data.empty:
        daily_mkt = period_data.groupby("date")["close"].mean()
        if len(daily_mkt) > 1:
            mkt_ret = (daily_mkt.iloc[-1] / daily_mkt.iloc[0]) - 1
        else:
            mkt_ret = 0.0
    else:
        mkt_ret = 0.0

    marker = " *" if abs(row["sharpe_ratio"]) > 2 * pp_std else ""
    print(f"  {row['test_start'].strftime('%Y-%m')} ~ {row['test_end'].strftime('%Y-%m')}:  "
          f"Sharpe={row['sharpe_ratio']:+.3f}  MaxDD={row['max_drawdown']:.1%}  "
          f"MktRet={mkt_ret:+.1%}  Trades={row['trade_count']:>4.0f}  "
          f"CostR={row['cost_ratio']:.2%}{marker}")

# ═══════════════════════════════════════════════════════════════════════
# Diagnostic 2: Continuous vs Walk-Forward gap (overfitting)
# Same time window comparison — only use the walk-forward test periods
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("DIAGNOSTIC 2: Continuous vs Walk-Forward Gap (same window)")
print(f"{'=' * 80}\n")

# Restrict continuous backtest to walk-forward test window only
wf_test_start = pp["test_start"].iloc[0]
wf_test_end = pp["test_end"].iloc[-1]
data_wf_window = data[
    (data["date"] >= wf_test_start) & (data["date"] <= wf_test_end)
].copy()

fn_cont = make_continuous_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                     industry_map=industry_map, min_peers=min_peers)

t0 = time.time()
cont_result = continuous_backtest(
    data_wf_window, fn_cont,
    dead_zone=0.015,
    industry_map=industry_map,
    trading_cost=default_tc,
)
cont_elapsed = time.time() - t0

cont_sharpe = cont_result["overall"]["sharpe_ratio"]
# Gap = how much WF outperforms continuous (in-sample) on the same window
# Positive gap = WF > continuous = normal (WF uses re-estimated params)
# Negative gap = WF < continuous = WF is worse despite in-sample advantage
gap = (wf_sharpe - cont_sharpe) / cont_sharpe if abs(cont_sharpe) > 1e-10 else 0.0

print(f"  Window: {wf_test_start.strftime('%Y-%m-%d')} ~ {wf_test_end.strftime('%Y-%m-%d')}")
print(f"  Continuous Sharpe (same window): {cont_sharpe:.3f}")
print(f"  Walk-Forward Sharpe:             {wf_sharpe:.3f}")
print(f"  Gap (WF - Continuous): {gap:+.1%}")
print(f"  Elapsed: {cont_elapsed:.1f}s")

if gap < -0.30:
    print(f"  ⚠ WF underperforms continuous by >30% — capital chaining drag or regime shift")
elif gap > 0.50:
    print(f"  ⚠ WF outperforms continuous by >50% — possible look-ahead bias in signal_fn")
else:
    print(f"  ✓ Gap within [-30%, +50%] — acceptable")

# ═══════════════════════════════════════════════════════════════════════
# Diagnostic 3: Cost Sensitivity
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("DIAGNOSTIC 3: Cost Sensitivity (Sharpe Elasticity)")
print(f"{'=' * 80}\n")

COST_SCENARIOS = [
    ("Baseline",  TradingCost(commission=0.0001, slippage_ticks=1)),
    ("Medium",    TradingCost(commission=0.0003, slippage_ticks=2)),
    ("High",      TradingCost(commission=0.0005, slippage_ticks=3)),
    ("Extreme",   TradingCost(commission=0.001,  slippage_ticks=5)),
    ("Worst",     TradingCost(commission=0.002,  slippage_ticks=8)),
]

cost_results = []
for label, tc in COST_SCENARIOS:
    total_cost_rate = tc.commission + tc.stamp_tax + tc.transfer_fee
    fn = make_earnings_signal_fn(top_n=10, bottom_n=5, rebalance=15,
                                  industry_map=industry_map, min_peers=min_peers)
    r = walk_forward_backtest(
        data, fn,
        train_months=12, test_months=3,
        dead_zone=0.015,
        industry_map=industry_map,
        trading_cost=tc,
    )
    ov = r["overall"]
    cost_results.append({
        "label": label,
        "commission": tc.commission,
        "slippage_ticks": tc.slippage_ticks,
        "total_cost_rate": total_cost_rate,
        "sharpe": ov["sharpe_ratio"],
        "ir": ov["per_period_ir"],
        "max_dd": ov["max_drawdown"],
    })
    print(f"  {label:<10} comm={tc.commission:.4f}  slip={tc.slippage_ticks}  "
          f"Sharpe={ov['sharpe_ratio']:.3f}  IR={ov['per_period_ir']:.3f}  "
          f"MaxDD={ov['max_drawdown']:.1%}")

# Sharpe elasticity: (ΔSharpe/Sharpe_base) / (ΔCost/Cost_base)
base = cost_results[0]
extreme = cost_results[3]  # "Extreme" scenario
if base["sharpe"] > 1e-10 and base["total_cost_rate"] > 1e-10:
    delta_sharpe = (base["sharpe"] - extreme["sharpe"]) / base["sharpe"]
    delta_cost = (extreme["total_cost_rate"] - base["total_cost_rate"]) / base["total_cost_rate"]
    elasticity = delta_sharpe / delta_cost if delta_cost > 1e-10 else 0.0
else:
    elasticity = 0.0

print(f"\n  Sharpe Elasticity (baseline→extreme): {elasticity:.2f}")
if elasticity < 1.0:
    print(f"  ✓ Elasticity < 1.0 — strategy is cost-robust")
elif elasticity < 2.0:
    print(f"  ~ Elasticity 1.0~2.0 — moderate cost sensitivity")
else:
    print(f"  ⚠ Elasticity > 2.0 — strategy highly dependent on low-cost environment")

# ═══════════════════════════════════════════════════════════════════════
# Diagnostic 4: Time Stability
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("DIAGNOSTIC 4: Time Stability")
print(f"{'=' * 80}\n")

# Split per-period Sharpes into first half / second half
n_periods = len(pp)
mid = n_periods // 2
first_half = pp.iloc[:mid]
second_half = pp.iloc[mid:]

fh_sharpe = first_half["sharpe_ratio"].mean() if len(first_half) > 0 else 0.0
fh_ir = (first_half["sharpe_ratio"].mean() / first_half["sharpe_ratio"].std()
         if len(first_half) > 1 and first_half["sharpe_ratio"].std() > 1e-10 else 0.0)
sh_sharpe = second_half["sharpe_ratio"].mean() if len(second_half) > 0 else 0.0
sh_ir = (second_half["sharpe_ratio"].mean() / second_half["sharpe_ratio"].std()
         if len(second_half) > 1 and second_half["sharpe_ratio"].std() > 1e-10 else 0.0)

# Linear regression on per-period Sharpe
x = np.arange(n_periods, dtype=float)
y = pp["sharpe_ratio"].values
if n_periods > 2:
    slope, intercept = np.polyfit(x, y, 1)
else:
    slope = 0.0

print(f"  First half  ({first_half['test_start'].iloc[0].strftime('%Y-%m')} ~ "
      f"{first_half['test_end'].iloc[-1].strftime('%Y-%m')}):  "
      f"Mean={fh_sharpe:.3f}  IR={fh_ir:.3f}")
print(f"  Second half ({second_half['test_start'].iloc[0].strftime('%Y-%m')} ~ "
      f"{second_half['test_end'].iloc[-1].strftime('%Y-%m')}):  "
      f"Mean={sh_sharpe:.3f}  IR={sh_ir:.3f}")
print(f"  Trend slope: {slope:+.4f} per period")

if slope < -0.05:
    print(f"  ⚠ Slope < -0.05 — factor may be decaying")
else:
    print(f"  ✓ Slope > -0.05 — no significant decay")

# ── Per-period Sharpe time series chart ────────────────────────────────
OUTPUT_DIR.mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(12, 5))

dates = pp["test_start"].values
sharpes = pp["sharpe_ratio"].values

ax.bar(range(len(sharpes)), sharpes, color="#4C72B0", alpha=0.7, label="Per-period Sharpe")
ax.axhline(y=pp_mean, color="#C44E52", linewidth=1.5, linestyle="--",
           label=f"Mean = {pp_mean:.3f}")
ax.axhline(y=pp_mean + pp_std, color="#C44E52", linewidth=0.8, linestyle=":",
           alpha=0.5, label=f"+1 Std = {pp_mean + pp_std:.3f}")
ax.axhline(y=pp_mean - pp_std, color="#C44E52", linewidth=0.8, linestyle=":",
           alpha=0.5, label=f"-1 Std = {pp_mean - pp_std:.3f}")

# Trend line
if n_periods > 2:
    trend_y = slope * x + intercept
    ax.plot(range(len(sharpes)), trend_y, color="#DD8452", linewidth=1.5,
            linestyle="-", label=f"Trend (slope={slope:+.4f})")

ax.set_xticks(range(len(sharpes)))
ax.set_xticklabels([pd.Timestamp(d).strftime("%Y-%m") for d in dates],
                    rotation=45, ha="right", fontsize=8)
ax.set_xlabel("Test Period")
ax.set_ylabel("Sharpe Ratio")
ax.set_title(f"Per-Period Sharpe Consistency  |  IR = {wf_ir:.3f}")
ax.legend(loc="upper right", fontsize=8)
ax.grid(axis="y", alpha=0.3)

fig.tight_layout()
fig.savefig(OUTPUT_DIR / "per_period_sharpe_timeseries.png", dpi=150)
print(f"\n  Chart saved: output/per_period_sharpe_timeseries.png")

# ═══════════════════════════════════════════════════════════════════════
# Decision Table
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 80}")
print("DECISION TABLE")
print(f"{'=' * 80}\n")

metrics = [
    ("IR (mean/std)", wf_ir, THRESHOLDS["IR"]),
    ("Cost Elasticity", elasticity, THRESHOLDS["Cost Elasticity"]),
    ("Trend Slope", slope, THRESHOLDS["Trend Slope"]),
    ("WF-Continuous Gap", gap, THRESHOLDS["WF-Continuous Gap"]),
]

header = f"  {'Metric':<25} {'Threshold':<12} {'Value':>10} {'Pass?':>8}"
print(header)
print("  " + "-" * (len(header) - 2))

all_pass = True
for name, value, (op, threshold) in metrics:
    if op == ">":
        passed = value > threshold
    else:
        passed = value < threshold
    all_pass = all_pass and passed

    threshold_str = f"{op} {threshold}"
    value_str = f"{value:.3f}"
    status = "  PASS" if passed else "  FAIL"
    print(f"  {name:<25} {threshold_str:<12} {value_str:>10} {status:>8}")

print()
if all_pass:
    print("  RESULT: All checks passed — strategy has live-trading potential")
else:
    failed = [name for name, value, (op, th) in metrics
              if (value > th if op == "<" else value < th)]
    print(f"  RESULT: {len(failed)} check(s) failed: {', '.join(failed)}")

print(f"\n{'=' * 80}")
