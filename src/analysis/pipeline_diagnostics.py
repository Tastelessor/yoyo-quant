"""Pipeline diagnostics: analyze signal quality and pipeline stage impact.

Reusable tools for diagnosing whether strategy signals have predictive power
and where signal degradation occurs in the risk/portfolio pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def signal_stage_counts(
    data: pd.DataFrame,
    raw_signals: pd.DataFrame,
    filtered_signals: pd.DataFrame,
    final_signals: pd.DataFrame,
) -> pd.DataFrame:
    """Compare signal counts at each pipeline stage.

    Parameters
    ----------
    data : DataFrame
        Market data with date, code columns.
    raw_signals : DataFrame
        Strategy output (date, code, signal, confidence).
    filtered_signals : DataFrame
        After filter_tradable.
    final_signals : DataFrame
        After enforce_t1.

    Returns
    DataFrame with columns: stage, buy, sell, hold, buy_pct, sell_pct.
    """
    n = len(data)
    stages = []
    for label, sig in [("raw", raw_signals), ("filtered", filtered_signals), ("final", final_signals)]:
        buy = (sig["signal"] == 1).sum()
        sell = (sig["signal"] == -1).sum()
        hold = (sig["signal"] == 0).sum()
        stages.append({
            "stage": label,
            "buy": buy,
            "sell": sell,
            "hold": hold,
            "buy_pct": buy / n * 100,
            "sell_pct": sell / n * 100,
        })
    return pd.DataFrame(stages)


def forward_return_analysis(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Analyze forward returns by signal type.

    Parameters
    ----------
    data : DataFrame
        Market data with date, code, close columns.
    signals : DataFrame
        Signals with date, code, signal columns.
    windows : list[int], optional
        Forward return windows in days. Default [1, 5, 20].

    Returns
    DataFrame with columns: signal_type, count, fwd_ret_Nd, hit_rate_Nd.
    """
    if windows is None:
        windows = [1, 5, 20]

    data = data.sort_values(["code", "date"]).reset_index(drop=True)
    for w in windows:
        data[f"fwd_ret_{w}d"] = (
            data.groupby("code")["close"]
            .pct_change(w)
            .shift(-w)
        )

    merged = data.merge(
        signals[["date", "code", "signal"]], on=["date", "code"], how="left",
    )
    merged["signal"] = merged["signal"].fillna(0)

    results = []
    for sig_val, label in [(1, "buy"), (-1, "sell"), (0, "hold")]:
        subset = merged[merged["signal"] == sig_val]
        row = {"signal_type": label, "count": len(subset)}
        for w in windows:
            col = f"fwd_ret_{w}d"
            valid = subset[col].dropna()
            row[f"fwd_ret_{w}d_mean"] = valid.mean() if len(valid) > 0 else np.nan
            row[f"fwd_ret_{w}d_median"] = valid.median() if len(valid) > 0 else np.nan
            row[f"hit_rate_{w}d"] = (valid > 0).mean() if len(valid) > 0 else np.nan
        results.append(row)

    return pd.DataFrame(results)


def signal_spread(forward_df: pd.DataFrame, window: int = 5) -> dict:
    """Compute signal spread: buy_mean_return - sell_mean_return.

    Returns dict with spread, buy_mean, sell_mean, and quality assessment.
    """
    col = f"fwd_ret_{window}d_mean"
    buy_row = forward_df[forward_df["signal_type"] == "buy"]
    sell_row = forward_df[forward_df["signal_type"] == "sell"]

    if buy_row.empty or sell_row.empty:
        return {"spread": np.nan, "quality": "insufficient_data"}

    buy_mean = buy_row[col].values[0]
    sell_mean = sell_row[col].values[0]
    spread = buy_mean - sell_mean

    buy_hit_col = f"hit_rate_{window}d"
    buy_hit = buy_row[buy_hit_col].values[0]

    if spread > 0.001 and buy_hit > 0.50:
        quality = "good"
    elif spread > 0:
        quality = "weak_but_directional"
    elif spread > -0.001:
        quality = "no_signal"
    else:
        quality = "inverted"

    return {
        "spread": spread,
        "buy_mean": buy_mean,
        "sell_mean": sell_mean,
        "buy_hit_rate": buy_hit,
        "quality": quality,
    }


def full_diagnosis(
    data: pd.DataFrame,
    raw_signals: pd.DataFrame,
    filtered_signals: pd.DataFrame,
    final_signals: pd.DataFrame,
) -> dict:
    """Run full pipeline diagnosis. Returns dict with all analysis results.

    Usage:
        result = full_diagnosis(data, raw, filtered, final)
        print(result["stage_counts"])
        print(result["forward_returns"])
        print(result["spread"])
    """
    stages = signal_stage_counts(data, raw_signals, filtered_signals, final_signals)
    fwd = forward_return_analysis(data, raw_signals)
    spread = signal_spread(fwd, window=5)

    return {
        "stage_counts": stages,
        "forward_returns": fwd,
        "spread": spread,
    }
