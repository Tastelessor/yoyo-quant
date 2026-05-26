"""Regime × factor category effectiveness matrix.

For each factor category (momentum, mean_reversion, volume_price, volatility,
vwap, trend), run a simple rank-based signal strategy, then split results by
regime to see which categories work in which market states.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import BacktestEngine
from src.context.regime import detect_regime
from src.data.filters import detect_limit_price, detect_suspension
from src.data.storage import load_parquet
from src.factors.mean_reversion import (
    calc_directional_balance_12d,
    calc_mfi_14d,
    calc_rsi_12d,
)
from src.factors.momentum import (
    calc_momentum_20d_change,
    calc_momentum_20d_return,
    calc_momentum_5d_ratio,
)
from src.factors.trend import calc_ma_slope_20d, calc_macd_like
from src.factors.volatility_gtja import (
    calc_atr_12d,
    calc_cci_12d,
    calc_volume_vol_20d,
)
from src.factors.volume_price_gtja import (
    calc_money_flow_6d,
    calc_obv_6d,
    calc_return_1d_times_vol,
    calc_shadow_ratio_20d,
    calc_up_down_vol_ratio_26d,
)
from src.factors.vwap import calc_vwap_close_ratio, calc_vwap_deviation
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable

CODES = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "600519", "000858",
    "000333", "600276", "300760", "600900", "601985", "300750",
    "002594", "000063",
]
RAW_DIR = Path("data/raw")

CATEGORIES = {
    "momentum": {
        "momentum_20d_return": calc_momentum_20d_return,
        "momentum_20d_change": calc_momentum_20d_change,
        "momentum_5d_ratio": calc_momentum_5d_ratio,
    },
    "mean_reversion": {
        "rsi_12d": calc_rsi_12d,
        "mfi_14d": calc_mfi_14d,
        "directional_balance_12d": calc_directional_balance_12d,
    },
    "volume_price": {
        "shadow_ratio_20d": calc_shadow_ratio_20d,
        "up_down_vol_26d": calc_up_down_vol_ratio_26d,
        "money_flow_6d": calc_money_flow_6d,
        "return_1d_times_vol": calc_return_1d_times_vol,
        "obv_6d": calc_obv_6d,
    },
    "volatility": {
        "atr_12d": calc_atr_12d,
        "cci_12d": calc_cci_12d,
        "volume_vol_20d": calc_volume_vol_20d,
    },
    "vwap": {
        "vwap_deviation": calc_vwap_deviation,
        "vwap_close_ratio": calc_vwap_close_ratio,
    },
    "trend": {
        "ma_slope_20d": calc_ma_slope_20d,
        "macd_like": calc_macd_like,
    },
}


def category_signal(
    data: pd.DataFrame,
    cat_factors: dict,
    rebalance: int = 20,
    top_n: int = 5,
    bottom_n: int = 3,
) -> pd.DataFrame:
    """Generate signals by averaging rank of all factors in a category."""
    df = data[["date", "code"]].copy()
    for name, func in cat_factors.items():
        df[name] = func(data).values

    dates = sorted(data["date"].unique())
    signal = pd.Series(0, index=data.index, dtype=int)
    confidence = pd.Series(0.0, index=data.index)

    min_window = 27
    rb_dates = [dates[i] for i in range(min_window, len(dates), rebalance)]

    for rb in rb_dates:
        day = df[df["date"] == rb].copy()
        if len(day) < 2:
            continue

        score = pd.Series(0.0, index=day.index)
        for name in cat_factors:
            score += day[name].rank(pct=True)
        score /= len(cat_factors)
        day["score"] = score
        day = day.sort_values("score", ascending=False)

        buys = set(day.head(top_n)["code"].tolist())
        sells = set(day.tail(bottom_n)["code"].tolist()) if bottom_n > 0 else set()

        rb_idx = dates.index(rb)
        next_rb = min(rb_idx + rebalance, len(dates))
        for h_date in dates[rb_idx:next_rb]:
            for c in buys:
                mask = (data["date"] == h_date) & (data["code"] == c)
                signal[mask] = 1
                sv = day[day["code"] == c]["score"]
                confidence[mask] = float(sv.values[0]) if len(sv) > 0 else 0.5
            for c in sells - buys:
                mask = (data["date"] == h_date) & (data["code"] == c)
                signal[mask] = -1
                confidence[mask] = 0.5

    # Warmup → hold
    early = data["date"] < dates[min_window]
    signal[early] = 0
    confidence[early] = 0.0

    return pd.DataFrame({
        "date": data["date"], "code": data["code"],
        "signal": signal, "confidence": confidence,
    })


def backtest(signals: pd.DataFrame, prices: pd.DataFrame, data: pd.DataFrame) -> dict:
    f = filter_tradable(data, signals)
    f = enforce_t1(f)
    pos = equal_weight(f, prices, capital=1_000_000)
    pos = apply_position_limit(pos, max_weight=0.3)
    engine = BacktestEngine(capital=1_000_000)
    return engine.run(pos, prices)["metrics"]


# ── Main ────────────────────────────────────────────────────────────────

print(f"Loading {len(CODES)} stocks...", end=" ", flush=True)
t0 = time.time()
frames = [
    load_parquet(RAW_DIR / f"{c}.parquet")
    for c in CODES
    if (RAW_DIR / f"{c}.parquet").exists()
]
data = pd.concat(frames, ignore_index=True)
data = detect_limit_price(data)
data = detect_suspension(data)
data = data.sort_values(["code", "date"]).reset_index(drop=True)
prices = data[["date", "code", "close"]]
print(f"{data.code.nunique()} stocks, {data.date.nunique()} days ({time.time() - t0:.0f}s)")

print("Detecting regime...", end=" ", flush=True)
t0 = time.time()
regime = detect_regime(data)
print(f"{time.time() - t0:.0f}s")
for rl, cnt in regime.value_counts().items():
    print(f"  {rl}: {cnt} days ({cnt / len(regime) * 100:.0f}%)")

print(f"\n{'Category':<18} {'Regime':<14} {'Sharpe':>8} {'AnnRet':>9} {'MaxDD':>8} {'WinRate':>8} {'Trades':>7}")
print("-" * 75)

rows = []
for cat_name, cat_funcs in CATEGORIES.items():
    full_sig = category_signal(data, cat_funcs)
    fm = backtest(full_sig, prices, data)
    rows.append({
        "category": cat_name, "regime": "ALL",
        "sharpe": fm["sharpe_ratio"], "ann_ret": fm["annual_return"],
        "max_dd": fm["max_drawdown"], "win_rate": fm["win_rate"],
        "trades": fm["trade_count"],
    })
    print(
        f"{cat_name:<18} {'ALL':<14} {fm['sharpe_ratio']:>8.3f} "
        f"{fm['annual_return']*100:>8.1f}% {fm['max_drawdown']*100:>7.1f}% "
        f"{fm['win_rate']*100:>7.1f}% {fm['trade_count']:>7d}"
    )

    # Per regime: filter signals to only regime-active dates
    for rl in ["trend_up", "trend_down", "range", "volatile"]:
        r_dates = set(regime[regime == rl].index)
        r_sig = full_sig[full_sig["date"].isin(r_dates)].copy()
        if r_sig.empty or r_sig["signal"].abs().sum() == 0:
            continue
        rm = backtest(r_sig, prices, data)
        rows.append({
            "category": cat_name, "regime": rl,
            "sharpe": rm["sharpe_ratio"], "ann_ret": rm["annual_return"],
            "max_dd": rm["max_drawdown"], "win_rate": rm["win_rate"],
            "trades": rm["trade_count"],
        })
        print(
            f"{'':<18} {rl:<14} {rm['sharpe_ratio']:>8.3f} "
            f"{rm['annual_return']*100:>8.1f}% {rm['max_drawdown']*100:>7.1f}% "
            f"{rm['win_rate']*100:>7.1f}% {rm['trade_count']:>7d}"
        )

# ── Analysis ────────────────────────────────────────────────────────────

df = pd.DataFrame(rows)

print(f"\n{'=' * 70}")
print("Best Category Per Regime (by Sharpe)")
for rl in ["ALL", "trend_up", "trend_down", "range", "volatile"]:
    sub = df[df["regime"] == rl]
    if sub.empty:
        continue
    best = sub.loc[sub["sharpe"].idxmax()]
    worst = sub.loc[sub["sharpe"].idxmin()]
    print(
        f"  {rl:<14} best={best['category']:<18} (Sharpe {best['sharpe']:+.3f})  "
        f"worst={worst['category']:<18} (Sharpe {worst['sharpe']:+.3f})"
    )

print(f"\nSharpe by Regime × Category:")
pivot = df.pivot(index="category", columns="regime", values="sharpe")
pivot = pivot[["ALL", "trend_up", "trend_down", "range", "volatile"]]
print(pivot.to_string(float_format=lambda x: f"{x:+.3f}"))

# Regime aversion score: std of Sharpe across regimes (lower = more regime-agnostic)
print(f"\nRegime Sensitivity (std of per-regime Sharpe, lower = more agnostic):")
regime_cols = ["trend_up", "trend_down", "range", "volatile"]
sensitivity = pivot[regime_cols].std(axis=1).sort_values()
for cat, val in sensitivity.items():
    print(f"  {cat:<18} std={val:.3f}")
