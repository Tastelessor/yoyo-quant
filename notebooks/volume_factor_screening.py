"""Quick screening: test individual volume/sentiment factors (10-year data, 30 stocks).

Reports results incrementally as each backtest completes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import BacktestEngine
from config.loader import load_config
from data import validate_ohlcv
from data.fetcher import fetch_daily
from data.filters import detect_limit_price, detect_suspension
from data.storage import load_parquet, save_parquet
from data.universe import resolve_universe
from portfolio.allocator import equal_weight
from risk.position_limit import apply_position_limit
from risk.tradability import enforce_t1, filter_tradable
from strategies.builtin.volume_price_gtja import GTJAVolumePriceStrategy

# ── config ──────────────────────────────────────────────────────────
cfg = load_config(Path(__file__).resolve().parent.parent / "configs" / "default.yaml")
universe_cfg = cfg.get("universe", {})
ALL_STOCKS = resolve_universe(universe_cfg)

# Use a diverse 30-stock subset for fast screening
SUBSET = [
    # 银行
    "601939", "601398", "600036",
    # 非银金融
    "601318", "300059", "600030",
    # 能源
    "601857", "601088", "601899",
    # 科技
    "688981", "688256", "002371",
    # 通信
    "600941", "300308", "000063",
    # 消费
    "600519", "000858", "000333",
    # 医药
    "600276", "300760",
    # 电力
    "600900", "601985",
    # 新能源
    "300750", "002594",
    # 电子制造
    "601138", "002475",
    # 装备制造
    "600150", "601668", "600031", "002352",
]

START = "2016-05-24"
END = "2026-05-24"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# ── load data ───────────────────────────────────────────────────────
print(f"Loading {len(SUBSET)} stocks from {START} to {END}...", flush=True)
t0 = time.time()
frames = []
for code in SUBSET:
    path = RAW_DIR / f"{code}.parquet"
    if path.exists():
        df = load_parquet(path)
    else:
        try:
            df = fetch_daily(code, START, END)
            save_parquet(df, path)
        except Exception:
            continue
    frames.append(df)

data = pd.concat(frames, ignore_index=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
prices = data[["date", "code", "close"]]
n_stocks = data["code"].nunique()
print(f"Loaded {len(data)} rows, {n_stocks} stocks in {time.time()-t0:.1f}s", flush=True)

# ── factor list ─────────────────────────────────────────────────────
ALL_FACTORS = [
    "money_flow_6d",              # GTJA #11 (existing)
    "up_down_vol_26d",            # GTJA #40 (existing)
    "obv_6d",                     # GTJA #43 (existing)
    "vol_rank_intraday_corr_6d",  # GTJA #1
    "vol_change_pct_5d",          # GTJA #80
    "return_6d_times_vol",        # GTJA #29
    "return_1d_times_vol",        # GTJA #178
    "high_vol_rank_corr_3d",      # GTJA #32
    "close_vol_rank_cov_5d",      # GTJA #99
    "open_vol_corr_10d",          # GTJA #139
    "vwap_vol_rank_corr_5d",      # GTJA #90
    "williams_r_smoothed_6d",     # GTJA #47
    "shadow_ratio_20d",           # GTJA #118
    "candle_body_vol_composite",  # GTJA #54
    "open_vwap_close_vwap",       # GTJA #12
    "dollar_vol_std_6d",          # GTJA #70
    "vol_macd_9_26_12",           # GTJA #145
    "vol_rsi_6d",                 # GTJA #102
]

BASELINE_FACTORS = ["money_flow_6d", "up_down_vol_26d", "obv_6d"]
TEST_FACTORS = [f for f in ALL_FACTORS if f not in BASELINE_FACTORS]


def make_weights(active: list[str]) -> dict:
    return {f: 1.0 if f in active else 0.0 for f in ALL_FACTORS}


def run_one(name: str, weights: dict) -> dict:
    """Run full pipeline for a single factor config."""
    strategy = GTJAVolumePriceStrategy(rebalance=20, top_n=5, bottom_n=3, weights=weights)
    signals = strategy.generate_signal(data)
    filtered = filter_tradable(data, signals)
    final = enforce_t1(filtered)
    positions = equal_weight(final, prices, capital=1_000_000)
    positions = apply_position_limit(positions, max_weight=0.3)
    engine = BacktestEngine(capital=1_000_000)
    result = engine.run(positions, prices)
    metrics = result["metrics"]
    return {
        "factor": name,
        **metrics,
    }


# ── run ─────────────────────────────────────────────────────────────
print(f"\nRunning 1 baseline + {len(TEST_FACTORS)} individual factor backtests...\n", flush=True)

results = []

# Baseline
print(f"[1/{len(TEST_FACTORS)+1}] BASELINE (3f)...", flush=True, end=" ")
t_start = time.time()
results.append(run_one("BASELINE (3f)", make_weights(BASELINE_FACTORS)))
print(f"Sharpe={results[-1]['sharpe_ratio']:.2f} in {time.time()-t_start:.1f}s", flush=True)

# Individual factors
for i, f in enumerate(TEST_FACTORS):
    print(f"[{i+2}/{len(TEST_FACTORS)+1}] {f}...", flush=True, end=" ")
    t_start = time.time()
    results.append(run_one(f, make_weights([f])))
    elapsed = time.time() - t_start
    s = results[-1]["sharpe_ratio"]
    print(f"Sharpe={s:.2f} in {elapsed:.1f}s", flush=True)

# ── display ─────────────────────────────────────────────────────────
baseline_sharpe = results[0]["sharpe_ratio"]

print()
print(f"{'Rank':<5} {'Factor':<34} {'Sharpe':>8} {'Ann.Ret':>8} {'MaxDD':>8} {'Trades':>7}")
print("-" * 80)
for i, row in enumerate(sorted(results, key=lambda r: r["sharpe_ratio"], reverse=True)):
    print(
        f"{i+1:<5} "
        f"{row['factor']:<34} "
        f"{row['sharpe_ratio']:>8.2f} "
        f"{row['annual_return']*100:>7.1f}% "
        f"{row['max_drawdown']*100:>7.1f}% "
        f"{row['trade_count']:>7}"
    )

print(f"\nBaseline Sharpe: {baseline_sharpe:.2f}")
print(f"{'Factor':<34} {'Sharpe':>8} {'Δ vs BL':>8}")
print("-" * 54)
for row in sorted(results, key=lambda r: r["sharpe_ratio"], reverse=True):
    if row["factor"] == "BASELINE (3f)":
        continue
    delta = row["sharpe_ratio"] - baseline_sharpe
    marker = " ▲" if delta > 0.03 else (" ▼" if delta < -0.03 else "")
    print(f"{row['factor']:<34} {row['sharpe_ratio']:>8.2f} {delta:>+7.2f}{marker}")

# ── save ────────────────────────────────────────────────────────────
output_dir = Path(__file__).resolve().parent / "output"
output_dir.mkdir(exist_ok=True)
pd.DataFrame(results).to_csv(output_dir / "factor_screening_quick.csv", index=False)
print(f"\nTotal time: {time.time()-t0:.0f}s")
print(f"Saved: {output_dir / 'factor_screening_quick.csv'}")
