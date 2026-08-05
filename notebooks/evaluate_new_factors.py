"""Evaluate new fundamental factors: value, quality, liquidity.

Runs walk-forward backtest for each factor individually,
then the combined fundamental_diversified strategy.
Outputs per-factor Sharpe/IR and cross-factor correlation matrix.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.walk_forward import compute_overall_metrics, walk_forward_backtest
from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.fetcher import (
    fetch_daily_batch,
    fetch_fundamentals,
    fetch_index_constituents,
)
from src.data.filters import detect_limit_price, detect_suspension
from src.data.fundamentals_quarterly import build_quality_panel, fetch_fina_batch
from src.data.trade_calendar import fetch_trade_dates
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

START_DATE = "2016-06-01"
END_DATE = "2026-05-22"


def build_data_panel(codes, start, end, raw_dir):
    """Build full data panel: OHLCV + fundamentals + earnings + quality."""
    print(f"Fetching OHLCV for {len(codes)} stocks...")
    data = fetch_daily_batch(codes, start, end, raw_dir)

    # Fetch fundamentals (PE, PB, total_mv) — per-date
    print("Fetching fundamentals...")
    trade_dates = list(fetch_trade_dates(START_DATE, END_DATE))
    fund_frames = []
    for d in trade_dates:
        d_str = pd.Timestamp(d).strftime("%Y-%m-%d")
        try:
            fdf = fetch_fundamentals(d_str, cache_dir=raw_dir / "fundamentals")
            fdf["date"] = d
            fund_frames.append(fdf)
        except Exception:
            pass
    if fund_frames:
        fund = pd.concat(fund_frames, ignore_index=True)
        data = data.merge(fund, on=["date", "code"], how="left")

    # Fetch and build earnings panel
    print("Fetching earnings...")
    earnings_df = fetch_earnings_history(
        codes, cache_dir=raw_dir / "earnings", sleep_sec=0.3, progress=True
    )
    trade_dates_dt = pd.DatetimeIndex(trade_dates)
    earnings_panel = build_earnings_panel(earnings_df, trade_dates_dt, codes)
    data = data.merge(earnings_panel, on=["date", "code"], how="left")

    # Fetch and build quality panel
    print("Fetching fina_indicator...")
    fina_df = fetch_fina_batch(
        codes, cache_dir=raw_dir / "fundamentals_quarterly", sleep_sec=0.3, progress=True
    )
    quality_panel = build_quality_panel(fina_df, trade_dates_dt, codes)
    data = data.merge(quality_panel, on=["date", "code"], how="left")

    # Add market state annotations
    data = detect_limit_price(data)
    data = detect_suspension(data)

    return data


def make_single_factor_signal_fn(factor_col, rebalance=15, top_n=10, bottom_n=5):
    """Strategy that uses a single factor for scoring."""
    def signal_fn(train_data, test_data):
        from src.strategies.builtin.earnings_surprise import (
            _rank_normalize,
            gtja_earnings_surprise_signal,
        )

        # Use the earnings surprise signal function pattern but with a single factor
        df = test_data.sort_values(["code", "date"]).reset_index(drop=True)
        all_dates = sorted(df["date"].unique())

        if factor_col not in df.columns:
            return pd.DataFrame(
                {"date": df["date"], "code": df["code"], "signal": 0, "confidence": 0.0}
            )

        signal = pd.Series(0, index=df.index, dtype=int)
        confidence = pd.Series(0.0, index=df.index)
        min_window = 21
        rebalance_dates = [
            all_dates[i] for i in range(min_window, len(all_dates), rebalance)
        ]

        for rb_date in rebalance_dates:
            day_mask = df["date"] == rb_date
            day_data = df[day_mask].copy()
            if len(day_data) < 2:
                continue

            day_data["score"] = _rank_normalize(day_data[factor_col])
            day_data = day_data.sort_values("score", ascending=False)

            buy_codes = (
                set(day_data.head(top_n)["code"].tolist()) if top_n > 0 else set()
            )
            sell_codes = (
                set(day_data.tail(bottom_n)["code"].tolist()) if bottom_n > 0 else set()
            )

            rb_idx = all_dates.index(rb_date)
            next_rb_idx = min(rb_idx + rebalance, len(all_dates))
            for h_date in all_dates[rb_idx:next_rb_idx]:
                h_mask = df["date"] == h_date
                for code in buy_codes:
                    mask = h_mask & (df["code"] == code)
                    idx = df.index[mask]
                    if len(idx) > 0:
                        signal.iloc[idx] = 1
                        sv = day_data[day_data["code"] == code]["score"].values
                        confidence.iloc[idx] = float(sv[0]) if len(sv) > 0 else 0.5
                for code in sell_codes - buy_codes:
                    mask = h_mask & (df["code"] == code)
                    idx = df.index[mask]
                    if len(idx) > 0:
                        signal.iloc[idx] = -1
                        confidence.iloc[idx] = 0.5

        if min_window < len(all_dates):
            first_valid = all_dates[min_window]
        else:
            first_valid = all_dates[-1]
        early = df["date"] < first_valid
        signal[early] = 0
        confidence[early] = 0.0

        return pd.DataFrame(
            {
                "date": df["date"],
                "code": df["code"],
                "signal": signal,
                "confidence": confidence,
            }
        )

    return signal_fn


def make_combined_signal_fn(top_n=10, bottom_n=5, rebalance=15):
    """Combined fundamental_diversified strategy."""
    def signal_fn(train_data, test_data):
        s = get_strategy(
            "fundamental_diversified",
            rebalance=rebalance, top_n=top_n, bottom_n=bottom_n,
        )
        return s.generate_signal(test_data)
    return signal_fn


def run_experiment(data, signal_fn, label, **wf_kwargs):
    """Run walk-forward and return metrics."""
    t0 = time.time()
    result = walk_forward_backtest(
        data, signal_fn,
        train_months=12, test_months=3,
        **wf_kwargs,
    )
    elapsed = time.time() - t0

    ov = result["overall"]
    return {
        "label": label,
        "overall_sharpe": ov.get("sharpe_ratio", 0),
        "annual_return": ov.get("annual_return", 0),
        "max_drawdown": ov.get("max_drawdown", 0),
        "per_period_ir": ov.get("per_period_ir", 0),
        "periods": result["per_period"].shape[0] if not result["per_period"].empty else 0,
        "elapsed": elapsed,
    }


def compute_factor_correlations(data, factor_cols):
    """Compute cross-factor correlation matrix on a single date."""
    sample_date = sorted(data["date"].unique())[len(data["date"].unique()) // 2]
    day = data[data["date"] == sample_date]
    available = [c for c in factor_cols if c in day.columns]
    if len(available) < 2:
        return pd.DataFrame()
    return day[available].corr()


def main():
    print("=" * 60)
    print("New Factor Evaluation: Value + Quality + Liquidity")
    print("=" * 60)

    # 1. Load universe
    codes = fetch_index_constituents("000300.SH", raw_dir=RAW_DIR / "index")
    print(f"CSI 300 constituents: {len(codes)} stocks")

    # 2. Build data panel
    data = build_data_panel(codes, START_DATE, END_DATE, RAW_DIR)
    print(f"Data shape: {data.shape}")
    print(f"Columns: {list(data.columns)}")

    # 3. Single-factor walk-forward evaluation
    factors_to_test = {
        "ep": "Value (EP)",
        "bp": "Value (BP)",
        "amihud": "Liquidity (Amihud)",
        "turnover": "Liquidity (Turnover)",
        "roe_level": "Quality (ROE Level)",
        "roe_stability": "Quality (ROE Stability)",
        "cashflow_quality": "Quality (Cashflow)",
        "earnings_surprise": "Earnings (Surprise)",
        "earnings_acceleration": "Earnings (Acceleration)",
    }

    results = []
    for factor_col, label in factors_to_test.items():
        if factor_col not in data.columns:
            print(f"  SKIP {label}: column '{factor_col}' not in data")
            continue
        print(f"\n  Running {label}...")
        signal_fn = make_single_factor_signal_fn(factor_col)
        res = run_experiment(data, signal_fn, label, dead_zone=0.02)
        results.append(res)
        print(f"    Sharpe={res['overall_sharpe']:.3f}  IR={res['per_period_ir']:.3f}  "
              f"MaxDD={res['max_drawdown']:.1%}")

    # 4. Combined strategy
    print("\n  Running Combined (fundamental_diversified)...")
    combined_fn = make_combined_signal_fn()
    # NOTE: fundamental_diversified 默认权重只保留评估后筛选的 3 个因子
    # (earnings_surprise/amihud/roe_stability)，此处标签按实际组合标注
    res = run_experiment(data, combined_fn, "Combined (fundamental_diversified, 3 factors)", dead_zone=0.02)
    results.append(res)
    print(f"    Sharpe={res['overall_sharpe']:.3f}  IR={res['per_period_ir']:.3f}  "
          f"MaxDD={res['max_drawdown']:.1%}")

    # 5. Results table
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("overall_sharpe", ascending=False)
    print(df_results.to_string(index=False))

    # 6. Cross-factor correlation
    all_factors = list(factors_to_test.keys())
    print("\n" + "=" * 60)
    print("FACTOR CORRELATION MATRIX")
    print("=" * 60)
    corr = compute_factor_correlations(data, all_factors)
    if not corr.empty:
        print(corr.round(3).to_string())

    # Save results
    out_dir = PROJECT_ROOT / "data" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    df_results.to_csv(out_dir / "new_factor_evaluation.csv", index=False)
    if not corr.empty:
        corr.to_csv(out_dir / "new_factor_correlation.csv")
    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
