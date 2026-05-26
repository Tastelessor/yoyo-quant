"""Run full factor audit, save to standardized format, update weights, backtest.

Usage: python notebooks/run_factor_audit.py

Outputs:
  data/audit/<date>_factor_audit.parquet  — full audit
  data/audit/<date>_audit_meta.json       — metadata
  data/audit/latest_factor_audit.parquet  — convenience symlink/copy
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.fetcher import fetch_daily
from src.data.storage import load_parquet, save_parquet
from src.data.filters import detect_limit_price, detect_suspension
from src.data import validate_ohlcv
from src.context.stock_selector import evaluate_factors
from src.strategies.builtin.volume_price_gtja import GTJAVolumePriceStrategy
from src.risk.tradability import enforce_t1, filter_tradable
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.backtest.engine import BacktestEngine

PROJECT = Path(__file__).resolve().parent.parent
AUDIT_DIR = PROJECT / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ──────────────────────────────────────────────────────────────
SUBSET = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "688256", "002371",
    "600941", "300308", "000063", "600519", "000858", "000333",
    "600276", "300760", "600900", "601985", "300750", "002594",
    "601138", "002475", "600150", "601668", "600031", "002352",
]
START, END = "2023-01-01", "2026-05-24"
RAW_DIR = PROJECT / "data" / "raw"

COLLECT_ALL = True  # set False to only audit registered factors

# ── Factor collection ───────────────────────────────────────────────────
def collect_all_factors():
    """Collect ALL factor functions from all factor modules."""
    factors = {}

    from src.factors.momentum import (
        calc_momentum_5d_change, calc_momentum_5d_ratio,
        calc_momentum_6d_return, calc_momentum_20d_change, calc_momentum_20d_return,
    )
    factors['momentum_5d_change'] = (calc_momentum_5d_change, 'momentum')
    factors['momentum_5d_ratio'] = (calc_momentum_5d_ratio, 'momentum')
    factors['momentum_6d_return'] = (calc_momentum_6d_return, 'momentum')
    factors['momentum_20d_change'] = (calc_momentum_20d_change, 'momentum')
    factors['momentum_20d_return'] = (calc_momentum_20d_return, 'momentum')

    from src.factors.mean_reversion import (
        calc_rsi_6d, calc_rsi_12d, calc_directional_balance_12d, calc_mfi_14d,
    )
    factors['rsi_6d'] = (calc_rsi_6d, 'mean_reversion')
    factors['rsi_12d'] = (calc_rsi_12d, 'mean_reversion')
    factors['directional_balance_12d'] = (calc_directional_balance_12d, 'mean_reversion')
    factors['mfi_14d'] = (calc_mfi_14d, 'mean_reversion')

    from src.factors.volume_price import calc_rsi, calc_obv, calc_volume_ratio, calc_atr
    factors['rsi_14d'] = (lambda df: calc_rsi(df, window=14), 'volume_price')
    factors['obv'] = (calc_obv, 'volume_price')
    factors['volume_ratio_20d'] = (lambda df: calc_volume_ratio(df, window=20), 'volume_price')
    factors['atr_14d_basic'] = (lambda df: calc_atr(df, window=14), 'volume_price')

    from src.factors.volatility import calc_hv
    factors['hv_20d'] = (calc_hv, 'volatility')

    from src.factors.volatility_gtja import (
        calc_cci_12d, calc_volume_vol_10d, calc_volume_vol_20d,
        calc_atr_12d, calc_atr_6d,
    )
    factors['cci_12d'] = (calc_cci_12d, 'volatility')
    factors['volume_vol_10d'] = (calc_volume_vol_10d, 'volatility')
    factors['volume_vol_20d'] = (calc_volume_vol_20d, 'volatility')
    factors['atr_12d'] = (calc_atr_12d, 'volatility')
    factors['atr_6d'] = (calc_atr_6d, 'volatility')

    from src.factors.vwap import calc_vwap_close_ratio, calc_vwap_deviation
    factors['vwap_close_ratio'] = (calc_vwap_close_ratio, 'vwap')
    factors['vwap_deviation'] = (calc_vwap_deviation, 'vwap')

    from src.factors.trend import calc_ma_slope_6d, calc_ma_slope_20d, calc_macd_like
    factors['ma_slope_6d'] = (calc_ma_slope_6d, 'trend')
    factors['ma_slope_20d'] = (calc_ma_slope_20d, 'trend')
    factors['macd_like'] = (calc_macd_like, 'trend')

    from src.factors.volume_price_gtja import (
        calc_money_flow_6d, calc_up_down_vol_ratio_26d, calc_obv_6d,
        calc_vol_rank_intraday_corr_6d, calc_vol_change_pct_5d,
        calc_return_6d_times_vol, calc_return_1d_times_vol,
        calc_high_vol_rank_corr_3d, calc_close_vol_rank_cov_5d,
        calc_open_vol_corr_10d, calc_vwap_vol_rank_corr_5d,
        calc_williams_r_smoothed_6d, calc_shadow_ratio_20d,
        calc_candle_body_vol_composite, calc_open_vwap_close_vwap,
        calc_dollar_vol_std_6d, calc_vol_macd_9_26_12, calc_vol_rsi_6d,
    )
    gtja = {
        'money_flow_6d': calc_money_flow_6d,
        'up_down_vol_26d': calc_up_down_vol_ratio_26d,
        'obv_6d': calc_obv_6d,
        'vol_rank_intraday_corr_6d': calc_vol_rank_intraday_corr_6d,
        'vol_change_pct_5d': calc_vol_change_pct_5d,
        'return_6d_times_vol': calc_return_6d_times_vol,
        'return_1d_times_vol': calc_return_1d_times_vol,
        'high_vol_rank_corr_3d': calc_high_vol_rank_corr_3d,
        'close_vol_rank_cov_5d': calc_close_vol_rank_cov_5d,
        'open_vol_corr_10d': calc_open_vol_corr_10d,
        'vwap_vol_rank_corr_5d': calc_vwap_vol_rank_corr_5d,
        'williams_r_smoothed_6d': calc_williams_r_smoothed_6d,
        'shadow_ratio_20d': calc_shadow_ratio_20d,
        'candle_body_vol_composite': calc_candle_body_vol_composite,
        'open_vwap_close_vwap': calc_open_vwap_close_vwap,
        'dollar_vol_std_6d': calc_dollar_vol_std_6d,
        'vol_macd_9_26_12': calc_vol_macd_9_26_12,
        'vol_rsi_6d': calc_vol_rsi_6d,
    }
    for name, func in gtja.items():
        factors[name] = (func, 'volume_price')

    return factors


# ── Load data ────────────────────────────────────────────────────────────
print("=" * 70)
print("Factor Audit + Weight Update + Backtest")
print("=" * 70)

print(f"\n[1/4] Loading {len(SUBSET)} stocks ({START} ~ {END})...", end=" ", flush=True)
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
print(f"{data['code'].nunique()} stocks, {data['date'].nunique()} days ({time.time() - t0:.1f}s)")

# ── Compute factors ─────────────────────────────────────────────────────
print(f"\n[2/4] Computing factors...", flush=True)
t0 = time.time()
all_factors = collect_all_factors()
fdf = pd.DataFrame({"date": data["date"], "code": data["code"]})
ok, fail = 0, 0
for name, (func, cat) in all_factors.items():
    try:
        fdf[f"f_{name}"] = func(data).values
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  SKIP {name}: {e}")
print(f"  {ok} ok, {fail} failed ({time.time() - t0:.1f}s)")

factor_cols = [c for c in fdf.columns if c.startswith("f_")]
name_map = {f"f_{k}": k for k in all_factors}

# ── Run audit ────────────────────────────────────────────────────────────
print(f"\n[3/4] Auditing {len(factor_cols)} factors (LB=60, stability≥0.3)...", flush=True)

AUDIT_PARAMS = {
    "lookback": 60,
    "lag": 5,
    "min_coverage": 0.8,
    "min_stability": 0.3,
    "min_dispersion": 0.10,
}

t0 = time.time()
audit = evaluate_factors(fdf, factor_cols, **AUDIT_PARAMS)
audit["name"] = audit["factor"].map(name_map)
audit["category"] = audit["name"].map(lambda n: all_factors.get(n, (None, "other"))[1])

# Compute stability-based weight: max(stability, 0) / sum(max(stability, 0))
# All factors with positive stability get weight proportional to their stability.
# Negative-stability factors get zero (worse than random).
audit["weight"] = 0.0
positive_stab = audit["stability"].clip(lower=0.0)
total_pos = positive_stab.sum()
if total_pos > 0:
    audit["weight"] = positive_stab / total_pos

# Sort by stability desc
audit = audit.sort_values("stability", ascending=False).reset_index(drop=True)
audit = audit[["name", "category", "coverage", "stability", "dispersion", "active", "weight"]]

print(f"  {audit['active'].sum()}/{len(audit)} active ({time.time() - t0:.1f}s)")

# ── Save to standardized format ─────────────────────────────────────────
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
audit_path = AUDIT_DIR / f"{today}_factor_audit.parquet"
meta_path = AUDIT_DIR / f"{today}_audit_meta.json"
latest_path = AUDIT_DIR / "latest_factor_audit.parquet"

audit.to_parquet(audit_path)

meta = {
    "date": today,
    "universe": f"{len(SUBSET)} stocks (CSI 300 subset)",
    "data_period": f"{START} ~ {END}",
    "parameters": AUDIT_PARAMS,
    "n_factors_total": len(audit),
    "n_factors_active": int(audit["active"].sum()),
    "mean_stability": float(audit["stability"].mean()),
    "median_stability": float(audit["stability"].median()),
    "categories": {
        cat: {
            "n_total": int(len(sub := audit[audit["category"] == cat])),
            "n_active": int(sub["active"].sum()),
            "mean_stability": float(sub["stability"].mean()),
        }
        for cat in sorted(audit["category"].unique())
    },
}
with open(meta_path, "w") as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)

# Copy to latest
import shutil
shutil.copy(audit_path, latest_path)

print(f"\n  Saved: {audit_path}")
print(f"  Saved: {meta_path}")
print(f"  Saved: {latest_path}")

# ── Print audit report ──────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Audit Report")
print(f"{'─' * 70}")
print(f"{'#':>3} {'Factor':<32} {'Cat':<16} {'Stab':>8} {'Disp':>7} {'Active':>7} {'Weight':>8}")
print("-" * 80)
for i, (_, row) in enumerate(audit.iterrows()):
    flag = "✓" if row["active"] else "✗"
    w = f"{row['weight']:.3f}" if row["active"] else "-"
    print(f"{i+1:>3} {row['name']:<32} {row['category']:<16} {row['stability']:>8.3f} {row['dispersion']:>7.3f} {flag:>7} {w:>8}")

# ── Category summary ────────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Category Summary")
print(f"{'─' * 70}")
print(f"{'Category':<18} {'#Total':>7} {'#Active':>9} {'Mean Stab':>10}")
print("-" * 48)
for cat in sorted(audit["category"].unique()):
    sub = audit[audit["category"] == cat]
    print(f"{cat:<18} {len(sub):>7} {int(sub['active'].sum()):>9} {sub['stability'].mean():>10.3f}")

# ── Build strategy weights for gtja_volume_price ────────────────────────
print(f"\n{'─' * 70}")
print("[4/4] Backtest with audit-based weights")
print(f"{'─' * 70}")

# Strategy short name → audit name mapping
WEIGHT_MAP = {
    "money_flow_6d": "money_flow_6d",
    "up_down_vol_26d": "up_down_vol_26d",
    "obv_6d": "obv_6d",
    "shadow_ratio_20d": "shadow_ratio_20d",
    "return_1d_times_vol": "return_1d_times_vol",
    "return_6d_times_vol": "return_6d_times_vol",
    "vol_rank_intraday_corr_6d": "vol_rank_intraday_corr_6d",
    "vol_change_pct_5d": "vol_change_pct_5d",
    "high_vol_rank_corr_3d": "high_vol_rank_corr_3d",
    "close_vol_rank_cov_5d": "close_vol_rank_cov_5d",
    "open_vol_corr_10d": "open_vol_corr_10d",
    "vwap_vol_rank_corr_5d": "vwap_vol_rank_corr_5d",
    "williams_r_smoothed_6d": "williams_r_smoothed_6d",
    "candle_body_vol_composite": "candle_body_vol_composite",
    "open_vwap_close_vwap": "open_vwap_close_vwap",
    "dollar_vol_std_6d": "dollar_vol_std_6d",
    "vol_macd_9_26_12": "vol_macd_9_26_12",
    "vol_rsi_6d": "vol_rsi_6d",
}

# Build weight dict from audit
audit_weights = {}
audit_lookup = dict(zip(audit["name"], audit["weight"]))
audit_active_lookup = dict(zip(audit["name"], audit["active"]))

for short_name, audit_name in WEIGHT_MAP.items():
    w = audit_lookup.get(audit_name, 0.0)
    audit_weights[short_name] = w  # includes tiny weights for noise factors, zero for negative

# Baseline: equal weight on original 5 defaults
BASELINE_DEFAULTS = {"money_flow_6d", "up_down_vol_26d", "obv_6d", "shadow_ratio_20d", "return_1d_times_vol"}
ALL_KEYS = list(WEIGHT_MAP.keys())
baseline_w = {k: 1.0 if k in BASELINE_DEFAULTS else 0.0 for k in ALL_KEYS}

# Stability-weighted: from audit
stab_w = audit_weights

def run_backtest(weights: dict, label: str) -> dict:
    s = GTJAVolumePriceStrategy(rebalance=20, top_n=5, bottom_n=3, weights=weights)
    signals = s.generate_signal(data)
    filt = filter_tradable(data, signals)
    final = enforce_t1(filt)
    pos = equal_weight(final, prices, capital=1_000_000)
    pos = apply_position_limit(pos, max_weight=0.3)
    engine = BacktestEngine(capital=1_000_000)
    m = engine.run(pos, prices)["metrics"]
    return {
        "label": label,
        "sharpe": m["sharpe_ratio"],
        "ann_ret": m["annual_return"],
        "max_dd": m["max_drawdown"],
        "win_rate": m["win_rate"],
        "trades": m["trade_count"],
        "total_ret": m["total_return"],
        "n_f": sum(1 for v in weights.values() if v > 0),
    }

print("\nRunning backtests...\n")
results = []
for w, label in [
    (baseline_w, "Equal (5 default)"),
    (stab_w, "Audit-weighted (active)"),
]:
    print(f"  {label}...", end=" ", flush=True)
    t0 = time.time()
    r = run_backtest(w, label)
    results.append(r)
    print(f"Sharpe={r['sharpe']:.2f} ({time.time() - t0:.0f}s)")

print(f"\n{'Scheme':<30} {'#F':>4} {'Sharpe':>8} {'Ann.Ret':>9} {'MaxDD':>9} {'WinRate':>9} {'Total':>9}")
print("-" * 85)
for r in results:
    print(
        f"{r['label']:<30} {r['n_f']:>4} "
        f"{r['sharpe']:>8.2f} {r['ann_ret']*100:>8.2f}% "
        f"{r['max_dd']*100:>8.2f}% {r['win_rate']*100:>8.1f}% "
        f"{r['total_ret']*100:>8.1f}%"
    )

# Print active factor weights
print(f"\nAudit-based weights ({sum(1 for v in stab_w.values() if v > 0)} active):")
for name in sorted(stab_w, key=lambda k: stab_w[k], reverse=True):
    w = stab_w[name]
    if w > 0:
        print(f"  {name:<32} {w:.4f}")
