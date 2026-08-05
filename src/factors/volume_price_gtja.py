"""GTJA 191 Alpha Factors — Volume-Price Relationship category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.operators import (
    corr,
    delay,
    delta,
    rank,
    rolling_cov,
    rolling_mean,
    rolling_std,
    rolling_sum,
    sma,
    ts_max,
    ts_min,
)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_money_flow_6d(df: pd.DataFrame) -> pd.Series:
    """6d money flow: sum(((close-low)-(high-close))/(high-low)*vol, 6).

    GTJA Factor #11. Directional pressure weighted by volume.
    """
    df = _prepare(df)
    hl_range = df["high"] - df["low"]
    # Avoid division by zero
    hl_range = hl_range.replace(0, np.nan)
    pressure = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl_range
    signed_vol = pressure * df["volume"]
    tmp = pd.concat([df[["code", "date"]], signed_vol.rename("val")], axis=1)
    return rolling_sum(tmp, "val", 6)


def calc_up_down_vol_ratio_26d(df: pd.DataFrame) -> pd.Series:
    """26d up-volume / down-volume ratio * 100.

    GTJA Factor #40.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    up_vol = df["volume"].where(delta > 0, 0.0)
    down_vol = df["volume"].where(delta < 0, 0.0)
    tmp_up = pd.concat([df[["code", "date"]], up_vol.rename("val")], axis=1)
    tmp_down = pd.concat([df[["code", "date"]], down_vol.rename("val")], axis=1)
    sum_up = rolling_sum(tmp_up, "val", 26)
    sum_down = rolling_sum(tmp_down, "val", 26)
    return (sum_up / sum_down * 100).replace([np.inf, -np.inf], 0.0)


def calc_obv_6d(df: pd.DataFrame) -> pd.Series:
    """6d OBV-like signed volume sum.

    GTJA Factor #43.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    signed = df["volume"].where(delta > 0, -df["volume"].where(delta < 0, 0.0))
    tmp = pd.concat([df[["code", "date"]], signed.rename("val")], axis=1)
    return rolling_sum(tmp, "val", 6)


def _calc_daily_vwap(df: pd.DataFrame) -> pd.Series:
    """Per-day typical price proxy for VWAP."""
    return (df["high"] + df["low"] + df["close"]) / 3


# ---------------------------------------------------------------------------
# New volume/sentiment factors
# ---------------------------------------------------------------------------


def calc_vol_change_pct_5d(df: pd.DataFrame) -> pd.Series:
    """5d volume change percentage: (vol - delay(vol,5)) / delay(vol,5) * 100.

    GTJA Factor #80.
    """
    df = _prepare(df)
    lag = delay(df, "volume", 5)
    result = (df["volume"] - lag) / lag * 100
    return result.replace([np.inf, -np.inf], np.nan)


def calc_return_6d_times_vol(df: pd.DataFrame) -> pd.Series:
    """6d return times volume: (close-delay(close,6))/delay(close,6)*vol.

    GTJA Factor #29.
    """
    df = _prepare(df)
    lag = delay(df, "close", 6)
    return (df["close"] - lag) / lag * df["volume"]


def calc_return_1d_times_vol(df: pd.DataFrame) -> pd.Series:
    """Daily return times volume: (close-delay(close,1))/delay(close,1)*vol.

    GTJA Factor #178.
    """
    df = _prepare(df)
    lag = delay(df, "close", 1)
    return (df["close"] - lag) / lag * df["volume"]


def calc_open_vol_corr_10d(df: pd.DataFrame) -> pd.Series:
    """Negative open-volume correlation: -1 * corr(open, vol, 10).

    GTJA Factor #139.
    """
    df = _prepare(df)
    return -1 * corr(df, "open", "volume", 10)


def calc_high_vol_rank_corr_3d(df: pd.DataFrame) -> pd.Series:
    """3d sum of high-volume rank correlation: -1*sum(rank(corr(rank(high),rank(vol),3)),3).

    GTJA Factor #32.
    """
    df = _prepare(df)
    r_high = rank(df, "high")
    r_vol = rank(df, "volume")
    tmp = pd.concat([df[["code", "date"]], r_high.rename("r_high"), r_vol.rename("r_vol")], axis=1)
    c = corr(tmp, "r_high", "r_vol", 3)
    c_tmp = pd.concat([df[["code", "date"]], c.rename("val")], axis=1)
    r_c = rank(c_tmp, "val")
    rc_tmp = pd.concat([df[["code", "date"]], r_c.rename("val")], axis=1)
    return -1 * rolling_sum(rc_tmp, "val", 3)


def calc_close_vol_rank_cov_5d(df: pd.DataFrame) -> pd.Series:
    """Close-volume rank covariance: -1*rank(cov(rank(close),rank(vol),5)).

    GTJA Factor #99.
    """
    df = _prepare(df)
    r_close = rank(df, "close")
    r_vol = rank(df, "volume")
    tmp = pd.concat([df[["code", "date"]], r_close.rename("r_close"), r_vol.rename("r_vol")], axis=1)
    cov_vals = rolling_cov(tmp, "r_close", "r_vol", 5)
    cov_tmp = pd.concat([df[["code", "date"]], cov_vals.rename("val")], axis=1)
    return -1 * rank(cov_tmp, "val")


def calc_vwap_vol_rank_corr_5d(df: pd.DataFrame) -> pd.Series:
    """VWAP-volume rank correlation: -1*rank(corr(rank(vwap),rank(vol),5)).

    GTJA Factor #90.
    """
    df = _prepare(df)
    vwap = _calc_daily_vwap(df)
    r_vwap = rank(
        pd.concat([df[["code", "date"]], vwap.rename("val")], axis=1), "val",
    )
    r_vol = rank(df, "volume")
    tmp = pd.concat([df[["code", "date"]], r_vwap.rename("r_vwap"), r_vol.rename("r_vol")], axis=1)
    c = corr(tmp, "r_vwap", "r_vol", 5)
    c_tmp = pd.concat([df[["code", "date"]], c.rename("val")], axis=1)
    return -1 * rank(c_tmp, "val")


def calc_vol_rank_intraday_corr_6d(df: pd.DataFrame) -> pd.Series:
    """Volume change rank vs intraday return rank correlation: -1*corr(rank(delta(log(vol),1)),rank((close-open)/open),6).

    GTJA Factor #1.
    """
    df = _prepare(df)
    log_vol = np.log(df["volume"].clip(lower=1))
    log_vol_tmp = pd.concat([df[["code", "date"]], log_vol.rename("val")], axis=1)
    d_log_vol = delta(log_vol_tmp, "val", 1)
    dlv_tmp = pd.concat([df[["code", "date"]], d_log_vol.rename("val")], axis=1)
    r_delta = rank(dlv_tmp, "val")

    intraday = (df["close"] - df["open"]) / df["open"]
    intraday_tmp = pd.concat([df[["code", "date"]], intraday.rename("val")], axis=1)
    r_intraday = rank(intraday_tmp, "val")

    tmp = pd.concat([df[["code", "date"]], r_delta.rename("r_delta"), r_intraday.rename("r_intraday")], axis=1)
    return -1 * corr(tmp, "r_delta", "r_intraday", 6)


def calc_williams_r_smoothed_6d(df: pd.DataFrame) -> pd.Series:
    """Williams %R-like smoothed: sma((tsmax(high,6)-close)/(tsmax(high,6)-tsmin(low,6))*100,9,1).

    GTJA Factor #47.
    """
    df = _prepare(df)
    hh = ts_max(df, "high", 6)
    ll = ts_min(df, "low", 6)
    denom = hh - ll
    denom = denom.replace(0, np.nan)
    wr = (hh - df["close"]) / denom * 100
    wr_tmp = pd.concat([df[["code", "date"]], wr.rename("val")], axis=1)
    return sma(wr_tmp, "val", 9, 1)


def calc_shadow_ratio_20d(df: pd.DataFrame) -> pd.Series:
    """Upper/lower shadow ratio: sum(high-open,20)/sum(open-low,20)*100.

    GTJA Factor #118.
    """
    df = _prepare(df)
    upper = df["high"] - df["open"]
    lower = df["open"] - df["low"]
    up_tmp = pd.concat([df[["code", "date"]], upper.rename("val")], axis=1)
    lo_tmp = pd.concat([df[["code", "date"]], lower.rename("val")], axis=1)
    sum_up = rolling_sum(up_tmp, "val", 20)
    sum_lo = rolling_sum(lo_tmp, "val", 20)
    result = sum_up / sum_lo * 100
    return result.replace([np.inf, -np.inf], 0.0)


def calc_candle_body_vol_composite(df: pd.DataFrame) -> pd.Series:
    """Candle body volatility composite: -1*rank(std(abs(close-open),10)+close-open+corr(close,open,10)).

    GTJA Factor #54.
    """
    df = _prepare(df)
    abs_body = (df["close"] - df["open"]).abs()
    body_tmp = pd.concat([df[["code", "date"]], abs_body.rename("val")], axis=1)
    body_std = rolling_std(body_tmp, "val", 10)
    gap = df["close"] - df["open"]
    oc_corr = corr(df, "close", "open", 10)
    composite = body_std + gap + oc_corr
    comp_tmp = pd.concat([df[["code", "date"]], composite.rename("val")], axis=1)
    return -1 * rank(comp_tmp, "val")


def calc_open_vwap_close_vwap(df: pd.DataFrame) -> pd.Series:
    """Open vs VWAP * close-VWAP distance: rank(open-sum(vwap,10)/10)*-1*rank(abs(close-vwap)).

    GTJA Factor #12.
    """
    df = _prepare(df)
    vwap = _calc_daily_vwap(df)
    vwap_tmp = pd.concat([df[["code", "date"]], vwap.rename("val")], axis=1)
    sum_vwap = rolling_sum(vwap_tmp, "val", 10)
    avg_vwap = sum_vwap / 10

    open_dev = df["open"] - avg_vwap
    open_dev_tmp = pd.concat([df[["code", "date"]], open_dev.rename("val")], axis=1)
    r_open = rank(open_dev_tmp, "val")

    close_dev = (df["close"] - vwap).abs()
    close_dev_tmp = pd.concat([df[["code", "date"]], close_dev.rename("val")], axis=1)
    r_close = rank(close_dev_tmp, "val")

    return r_open * -1 * r_close


def calc_dollar_vol_std_6d(df: pd.DataFrame) -> pd.Series:
    """Dollar volume volatility: std(vol*vwap,6).

    GTJA Factor #70.
    """
    df = _prepare(df)
    vwap = _calc_daily_vwap(df)
    dollar_vol = df["volume"] * vwap
    dv_tmp = pd.concat([df[["code", "date"]], dollar_vol.rename("val")], axis=1)
    return rolling_std(dv_tmp, "val", 6)


def calc_vol_macd_9_26_12(df: pd.DataFrame) -> pd.Series:
    """Volume MACD: (mean(vol,9)-mean(vol,26))/mean(vol,12)*100.

    GTJA Factor #145.
    """
    df = _prepare(df)
    vol_tmp = pd.concat([df[["code", "date"]], df["volume"].rename("val")], axis=1)
    ma9 = rolling_mean(vol_tmp, "val", 9)
    ma26 = rolling_mean(vol_tmp, "val", 26)
    ma12 = rolling_mean(vol_tmp, "val", 12)
    result = (ma9 - ma26) / ma12 * 100
    return result.replace([np.inf, -np.inf], 0.0)


def calc_vol_rsi_6d(df: pd.DataFrame) -> pd.Series:
    """Volume RSI: sma(max(vol-delay(vol,1),0),6,1)/sma(abs(vol-delay(vol,1)),6,1)*100.

    GTJA Factor #102.
    """
    df = _prepare(df)
    diff = df["volume"] - delay(df, "volume", 1)
    up = diff.clip(lower=0)
    abs_diff = diff.abs()
    up_tmp = pd.concat([df[["code", "date"]], up.rename("val")], axis=1)
    abs_tmp = pd.concat([df[["code", "date"]], abs_diff.rename("val")], axis=1)
    sma_up = sma(up_tmp, "val", 6, 1)
    sma_abs = sma(abs_tmp, "val", 6, 1)
    result = sma_up / sma_abs * 100
    return result.replace([np.inf, -np.inf], 0.0)
