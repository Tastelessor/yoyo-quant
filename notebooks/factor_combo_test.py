"""Test factor combinations of top performers from screening."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.loader import load_config
from src.data.fetcher import fetch_daily
from src.data.storage import save_parquet, load_parquet
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.data import validate_ohlcv
from src.strategies.builtin.volume_price_gtja import GTJAVolumePriceStrategy
from src.risk.tradability import enforce_t1, filter_tradable
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.backtest.engine import BacktestEngine

cfg = load_config(Path(__file__).resolve().parent.parent / "configs" / "default.yaml")
SUBSET = [
    "601939", "601398", "600036", "601318", "300059", "600030",
    "601857", "601088", "601899", "688981", "688256", "002371",
    "600941", "300308", "000063", "600519", "000858", "000333",
    "600276", "300760", "600900", "601985", "300750", "002594",
    "601138", "002475", "600150", "601668", "600031", "002352",
]
START, END = "2016-05-24", "2026-05-24"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

print(f"Loading {len(SUBSET)} stocks...", flush=True)
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
print(f"Loaded {data['code'].nunique()} stocks in {time.time()-t0:.1f}s", flush=True)

ALL_FACTORS = [
    "money_flow_6d", "up_down_vol_26d", "obv_6d",
    "return_1d_times_vol", "shadow_ratio_20d", "vol_macd_9_26_12",
    "high_vol_rank_corr_3d", "candle_body_vol_composite", "dollar_vol_std_6d",
    "open_vol_corr_10d", "return_6d_times_vol", "close_vol_rank_cov_5d",
    "vwap_vol_rank_corr_5d", "vol_rsi_6d", "vol_rank_intraday_corr_6d",
    "williams_r_smoothed_6d", "vol_change_pct_5d", "open_vwap_close_vwap",
]

BASELINE = ["money_flow_6d", "up_down_vol_26d", "obv_6d"]
TOP2 = ["shadow_ratio_20d", "return_1d_times_vol"]
TOP3 = ["shadow_ratio_20d", "return_1d_times_vol", "vol_macd_9_26_12"]
TOP5 = ["shadow_ratio_20d", "return_1d_times_vol", "vol_macd_9_26_12",
        "high_vol_rank_corr_3d", "candle_body_vol_composite"]

COMBOS = [
    ("BASELINE (3f)", BASELINE),
    ("TOP2 only (#118+#178)", TOP2),
    ("TOP3 (#118+#178+#145)", TOP3),
    ("BASELINE + TOP2", BASELINE + TOP2),
    ("TOP5", TOP5),
    ("ALL", ALL_FACTORS),
]


def make_weights(active: list[str]) -> dict:
    return {f: 1.0 if f in active else 0.0 for f in ALL_FACTORS}


def run_one(name: str, weights: dict) -> dict:
    strategy = GTJAVolumePriceStrategy(rebalance=20, top_n=5, bottom_n=3, weights=weights)
    signals = strategy.generate_signal(data)
    filtered = filter_tradable(data, signals)
    final = enforce_t1(filtered)
    positions = equal_weight(final, prices, capital=1_000_000)
    positions = apply_position_limit(positions, max_weight=0.3)
    engine = BacktestEngine(capital=1_000_000)
    m = engine.run(positions, prices)["metrics"]
    return {"name": name, **m}


print(f"\nTesting {len(COMBOS)} combinations...\n", flush=True)
results = []
for name, active in COMBOS:
    print(f"  {name} ({len(active)}f)...", flush=True, end=" ")
    t_start = time.time()
    results.append(run_one(name, make_weights(active)))
    s = results[-1]["sharpe_ratio"]
    print(f"Sharpe={s:.2f} in {time.time()-t_start:.0f}s", flush=True)

baseline_sharpe = results[0]["sharpe_ratio"]

print()
print(f"{'Rank':<5} {'Combo':<30} {'#F':>3} {'Sharpe':>8} {'Ann.Ret':>8} {'MaxDD':>8} {'Δ BL':>8}")
print("-" * 80)
for i, r in enumerate(sorted(results, key=lambda x: x["sharpe_ratio"], reverse=True)):
    delta = r["sharpe_ratio"] - baseline_sharpe
    print(
        f"{i+1:<5} {r['name']:<30} "
        f"{len(r['name'].split('+')):>3} "
        f"{r['sharpe_ratio']:>8.2f} "
        f"{r['annual_return']*100:>7.1f}% "
        f"{r['max_drawdown']*100:>7.1f}% "
        f"{delta:>+7.2f}"
    )

print(f"\nTotal: {time.time()-t0:.0f}s")
