"""Test stability-weighted factor combination against equal-weight baseline.

Key hypothesis: using factor audit stability scores as weights should
improve or match equal-weight without requiring grid search over combinations.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import BacktestEngine
from data import validate_ohlcv
from data.fetcher import fetch_daily
from data.filters import detect_limit_price, detect_suspension
from data.storage import load_parquet, save_parquet
from portfolio.allocator import equal_weight
from risk.position_limit import apply_position_limit
from risk.tradability import enforce_t1, filter_tradable
from strategies.builtin.volume_price_gtja import GTJAVolumePriceStrategy

SUBSET = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "688256", "002371",
    "600941", "300308", "000063", "600519", "000858", "000333",
    "600276", "300760", "600900", "601985", "300750", "002594",
    "601138", "002475", "600150", "601668", "600031", "002352",
]
START, END = "2023-01-01", "2026-05-24"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

print("Loading data...", end=" ", flush=True)
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
print(f"{data['code'].nunique()} stocks ({time.time() - t0:.1f}s)")

# Load audit
audit = pd.read_parquet(Path(__file__).resolve().parent.parent / "data" / "factor_audit.parquet")

# Map audit factor names to strategy short names
NAME_MAP = {
    "up_down_vol_26d": "up_down_vol_26d",
    "shadow_ratio_20d": "shadow_ratio_20d",
    "obv_6d": "obv_6d",
    "money_flow_6d": "money_flow_6d",
    "return_6d_times_vol": "return_6d_times_vol",
    "return_1d_times_vol": "return_1d_times_vol",
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

stab_map = {}
for _, row in audit.iterrows():
    name = row["name"]
    if name in NAME_MAP:
        stab_map[NAME_MAP[name]] = max(row["stability"], 0.01)

ALL_KEYS = list(NAME_MAP.values())


def run(weights: dict, label: str) -> dict:
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
        "n_f": sum(1 for v in weights.values() if v > 0),
    }


# 3 schemes
baseline_w = {
    k: 1.0 if k in {"money_flow_6d", "up_down_vol_26d", "obv_6d", "shadow_ratio_20d", "return_1d_times_vol"}
    else 0.0 for k in ALL_KEYS
}
stab_w = {k: stab_map.get(k, 0.0) for k in ALL_KEYS}
active_w = {k: stab_map[k] if stab_map.get(k, 0) >= 0.3 else 0.0 for k in ALL_KEYS}

print("\nTesting 3 weight schemes:\n")
results = []
for w, label in [
    (baseline_w, "Equal (5 default)"),
    (stab_w, "Stability-wtd (all 18)"),
    (active_w, "Stability-wtd (active)"),
]:
    print(f"  {label}...", end=" ", flush=True)
    t0 = time.time()
    r = run(w, label)
    results.append(r)
    print(f"Sharpe={r['sharpe']:.2f} in {time.time() - t0:.0f}s")

print(f"\n{'Scheme':<30} {'#F':>4} {'Sharpe':>8} {'Ann.Ret':>9} {'MaxDD':>9} {'WinRate':>9}")
print("-" * 75)
for r in results:
    print(
        f"{r['label']:<30} {r['n_f']:>4} "
        f"{r['sharpe']:>8.2f} {r['ann_ret']*100:>8.2f}% "
        f"{r['max_dd']*100:>8.2f}% {r['win_rate']*100:>8.1f}%"
    )
