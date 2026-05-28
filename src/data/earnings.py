"""Point-in-Time fundamental earnings event pipeline.

Fetches earnings forecasts and express reports from tushare,
computes PIT surprise via rolling pool state machine,
and builds a daily panel with cross-sectional Z-Score standardization.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_PROXY_URL = "http://124.222.60.121:8020/"

# Forecast type → surprise score (same scale as rank - 0.5)
FORECAST_TYPE_SCORE: dict[str, float] = {
    "预增": 0.5,
    "略增": 0.25,
    "扭亏": 0.35,
    "续盈": 0.05,
    "略减": -0.25,
    "预减": -0.5,
    "首亏": -0.5,
    "续亏": -0.35,
}

# Season-end MMDD → lambda(year) producing prev season end_date
_PREV_END_DATE_FN: dict[str, callable] = {
    "0331": lambda y: f"{y - 1}1231",  # Q1 → prev year annual
    "0630": lambda y: f"{y}0331",      # Q2 → Q1
    "0930": lambda y: f"{y}0630",      # Q3 → Q2
    "1231": lambda y: f"{y}0930",      # Q4 → Q3
}


def get_prev_end_date(end_date_str: str) -> str | None:
    """Compute previous season's end_date with cross-year linking for Q1.

    Q1 (0331) → previous year's annual (1231).
    Returns None if end_date_str is invalid or has no predecessor.
    """
    if pd.isna(end_date_str):
        return None
    s = str(end_date_str)
    if len(s) < 8:
        return None
    year = int(s[:4])
    mmdd = s[4:]
    fn = _PREV_END_DATE_FN.get(mmdd)
    if fn is None:
        return None
    return fn(year)


def _to_ts_code(code: str) -> str:
    """Convert 6-digit code to tushare format."""
    if code.startswith("6"):
        return f"{code}.SH"
    return f"{code}.SZ"


def fetch_forecast(
    ts_code: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Fetch earnings forecast data for a single stock from tushare.

    Parameters
    ----------
    ts_code : str
        Stock code (6-digit, e.g. "000001") or tushare format ("000001.SZ").
    cache_dir : Path | str | None
        Cache directory. Defaults to data/raw/earnings/forecast/.

    Returns
    -------
    DataFrame
        Columns: code, ann_date, end_date, forecast_type, predicted_profit.
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "earnings" / "forecast"
    else:
        cache_dir = Path(cache_dir)

    code = ts_code.split(".")[0] if "." in ts_code else ts_code
    cache_file = cache_dir / f"{code}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_fmt = _to_ts_code(code) if "." not in ts_code else ts_code
    raw = api.forecast(
        ts_code=ts_fmt,
        fields="ts_code,ann_date,end_date,type,p_change_min,p_change_max,"
               "net_profit_min,net_profit_max",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["code", "ann_date", "end_date", "forecast_type", "predicted_profit"]
        )

    df = raw.rename(columns={"ts_code": "code", "type": "forecast_type"})
    df["code"] = df["code"].str.split(".").str[0]
    df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")
    df["predicted_profit"] = (
        df[["net_profit_min", "net_profit_max"]].mean(axis=1, skipna=True)
    )

    result = df[["code", "ann_date", "end_date", "forecast_type", "predicted_profit"]].copy()
    cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_file, index=False)
    return result


def fetch_express(
    ts_code: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Fetch earnings express report data for a single stock from tushare.

    Parameters
    ----------
    ts_code : str
        Stock code (6-digit or tushare format).
    cache_dir : Path | str | None
        Cache directory. Defaults to data/raw/earnings/express/.

    Returns
    -------
    DataFrame
        Columns: code, ann_date, end_date, actual_profit, increase_rate.
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "earnings" / "express"
    else:
        cache_dir = Path(cache_dir)

    code = ts_code.split(".")[0] if "." in ts_code else ts_code
    cache_file = cache_dir / f"{code}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_fmt = _to_ts_code(code) if "." not in ts_code else ts_code
    raw = api.express(
        ts_code=ts_fmt,
        fields="ts_code,ann_date,end_date,n_income_attr_p,increase_rate,"
               "revenue,operate_profit,total_profit",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["code", "ann_date", "end_date", "actual_profit", "increase_rate"]
        )

    df = raw.rename(columns={"ts_code": "code"})
    df["code"] = df["code"].str.split(".").str[0]
    df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")

    # Map available profit columns to actual_profit
    if "n_income_attr_p" in df.columns:
        df["actual_profit"] = df["n_income_attr_p"]
    elif "total_profit" in df.columns:
        df["actual_profit"] = df["total_profit"]
    else:
        df["actual_profit"] = np.nan

    if "increase_rate" not in df.columns:
        df["increase_rate"] = np.nan

    result = df[["code", "ann_date", "end_date", "actual_profit", "increase_rate"]].copy()
    cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_file, index=False)
    return result


def fetch_earnings_history(
    codes: list[str],
    cache_dir: Path | str | None = None,
    sleep_sec: float = 0.5,
    progress: bool = True,
) -> pd.DataFrame:
    """Fetch all earnings data for a list of stock codes.

    Iterates over each stock, fetching forecast and express data.
    Forecast and Express are kept as independent rows (not merged).

    Parameters
    ----------
    codes : list[str]
        Stock codes (6-digit, e.g. ["000001", "600519"]).
    cache_dir : Path | str | None
        Cache directory. Defaults to data/raw/earnings/.
    sleep_sec : float
        Sleep between API calls for rate limiting.
    progress : bool
        Whether to log progress.

    Returns
    -------
    DataFrame
        Columns: code, ann_date, end_date, event_type,
                 predicted_profit, actual_profit, forecast_type.
    """
    import time

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "earnings"
    else:
        cache_dir = Path(cache_dir)

    cache_file = cache_dir / f"all_earnings_{'_'.join(sorted(codes)[:5])}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    all_frames = []
    fetched = 0

    for i, code in enumerate(codes):
        try:
            fc = fetch_forecast(code, cache_dir=cache_dir / "forecast")
            if len(fc) > 0:
                fc = fc.copy()
                fc["event_type"] = "forecast"
                fc["actual_profit"] = np.nan
                all_frames.append(fc)
                fetched += 1
        except Exception as e:
            logger.warning("Failed to fetch forecast for %s: %s", code, e)

        if fetched > 0 and sleep_sec > 0:
            time.sleep(sleep_sec)

        try:
            ex = fetch_express(code, cache_dir=cache_dir / "express")
            if len(ex) > 0:
                ex = ex.copy()
                ex["event_type"] = "express"
                ex["forecast_type"] = None
                all_frames.append(ex)
                fetched += 1
        except Exception as e:
            logger.warning("Failed to fetch express for %s: %s", code, e)

        if fetched > 0 and sleep_sec > 0:
            time.sleep(sleep_sec)

        if progress and (i + 1) % 20 == 0:
            logger.info("Fetched earnings for %d / %d stocks", i + 1, len(codes))

    if not all_frames:
        return pd.DataFrame(
            columns=["code", "ann_date", "end_date", "event_type",
                     "predicted_profit", "actual_profit", "forecast_type"]
        )

    result = pd.concat(all_frames, ignore_index=True)
    result = result.sort_values(["ann_date", "end_date"]).reset_index(drop=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_file, index=False)
    return result


def _compute_pit_surprise(events_df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time rolling pool state machine.

    Forecast events → FORECAST_TYPE_SCORE (no actual ranking).
    Express events → rank(actual) - rank(predicted) within express_pool (same N).
    Pool < 3 express peers → falls back to FORECAST_TYPE_SCORE.
    """
    df = events_df.copy()
    df["code"] = df["code"].astype(str)
    df = df.sort_values(["ann_date", "end_date"]).reset_index(drop=True)

    # Pools: {end_date: {code: {"predicted": float, "actual": float, "forecast_type": str}}}
    pools: dict[str, dict[str, dict]] = {}

    raw_surprise = np.full(len(df), np.nan)

    for i in range(len(df)):
        row = df.iloc[i]
        ed = str(row["end_date"])
        cd = row["code"]
        ev_type = row["event_type"]

        season_pool = pools.setdefault(ed, {})
        snap = season_pool.setdefault(cd, {
            "predicted": None, "actual": None, "forecast_type": None,
        })

        if ev_type == "forecast":
            snap["predicted"] = row["predicted_profit"]
            snap["forecast_type"] = row["forecast_type"]
            raw_surprise[i] = FORECAST_TYPE_SCORE.get(row["forecast_type"], 0.0)

        elif ev_type == "express":
            snap["actual"] = row["actual_profit"]
            if pd.notna(row.get("predicted_profit")):
                snap["predicted"] = row["predicted_profit"]

            # Collect express peers: stocks with both actual and predicted
            valid_peers = {
                k: v for k, v in season_pool.items()
                if v["actual"] is not None and v["predicted"] is not None
            }

            if len(valid_peers) >= 3 and cd in valid_peers:
                peer_codes = list(valid_peers.keys())
                acts = pd.Series(
                    {c: valid_peers[c]["actual"] for c in peer_codes}
                )
                preds = pd.Series(
                    {c: valid_peers[c]["predicted"] for c in peer_codes}
                )
                rank_act = acts.rank(pct=True).loc[cd]
                rank_pred = preds.rank(pct=True).loc[cd]
                raw_surprise[i] = rank_act - rank_pred
            else:
                # Pool too small → fallback to type score
                raw_surprise[i] = FORECAST_TYPE_SCORE.get(
                    snap.get("forecast_type") or row.get("forecast_type"), 0.0
                )

    df["raw_surprise"] = raw_surprise
    return df


def _compute_acceleration(df_surprise: pd.DataFrame) -> pd.DataFrame:
    """Seasonal acceleration via explicit prev_end_date matching.

    acceleration = surprise(current season) - surprise(previous season).
    Q1 → prev year annual. Missing prev → 0.0.
    """
    df = df_surprise.copy()
    df["prev_end_date"] = df["end_date"].astype(str).map(get_prev_end_date)

    # Self-join to get previous season's surprise
    df_prev = df[["code", "end_date", "raw_surprise"]].rename(
        columns={"end_date": "prev_end_date", "raw_surprise": "prev_surprise"}
    )
    # Keep last occurrence per (code, prev_end_date)
    df_prev = df_prev.drop_duplicates(subset=["code", "prev_end_date"], keep="last")

    df = df.merge(df_prev, on=["code", "prev_end_date"], how="left")
    df["raw_acceleration"] = (df["raw_surprise"] - df["prev_surprise"]).fillna(0.0)
    df = df.drop(columns=["prev_surprise"])
    return df


def build_earnings_panel(
    earnings_df: pd.DataFrame,
    trade_dates: pd.DatetimeIndex,
    codes: list[str],
) -> pd.DataFrame:
    """Build daily earnings panel with PIT surprise and Z-Score standardization.

    Pipeline:
    1. PIT surprise computation (rolling pool state machine)
    2. Seasonal acceleration (explicit prev_end_date matching)
    3. Sort by (ann_date, end_date) so newer seasons win on same-day collision
    4. merge_asof backward to daily panel
    5. Daily cross-sectional Z-Score standardization, clip [-3, 3]

    Returns
    -------
    DataFrame
        Columns: date, code, earnings_surprise, earnings_acceleration.
    """
    if earnings_df.empty:
        grid = pd.MultiIndex.from_product(
            [trade_dates, codes], names=["date", "code"]
        ).to_frame(index=False)
        grid["earnings_surprise"] = 0.0
        grid["earnings_acceleration"] = 0.0
        return grid.sort_values(["date", "code"]).reset_index(drop=True)

    # Step 1: PIT surprise
    df = _compute_pit_surprise(earnings_df)

    # Step 2: Acceleration
    df = _compute_acceleration(df)

    # Step 3: Sort so newer end_date wins on same ann_date (April collision fix)
    df = df.sort_values(["ann_date", "end_date"]).reset_index(drop=True)

    # Step 4: merge_asof to daily panel
    events = df[["ann_date", "code", "raw_surprise", "raw_acceleration"]].copy()
    events["code"] = events["code"].astype(str)
    events["ann_date"] = pd.to_datetime(events["ann_date"]).astype("datetime64[ns]")
    events = events.rename(
        columns={"ann_date": "date", "raw_surprise": "earnings_surprise",
                 "raw_acceleration": "earnings_acceleration"}
    )

    grid = pd.MultiIndex.from_product(
        [trade_dates, codes], names=["date", "code"]
    ).to_frame(index=False)
    grid["code"] = grid["code"].astype(str)
    grid["date"] = pd.to_datetime(grid["date"]).astype("datetime64[ns]")
    grid = grid.sort_values("date").reset_index(drop=True)

    panel = pd.merge_asof(
        grid.sort_values("date"),
        events.sort_values("date"),
        on="date",
        by="code",
        direction="backward",
    )

    # Step 5: Daily cross-sectional Z-Score standardization
    # Only apply Z-Score on dates with >= 2 non-NaN values;
    # dates with 0 or 1 non-NaN keep raw values (or 0.0 if all NaN)
    for col in ["earnings_surprise", "earnings_acceleration"]:
        non_nan_count = panel.groupby("date")[col].transform("count")
        means = panel.groupby("date")[col].transform("mean")
        stds = panel.groupby("date")[col].transform("std")

        # Only Z-Score where count >= 2 and std > 0
        do_zscore = (non_nan_count >= 2) & (stds > 0)
        z = np.where(do_zscore, np.clip((panel[col] - means) / stds, -3.0, 3.0), panel[col])
        panel[col] = pd.Series(z, index=panel.index).fillna(0.0)

    return panel[["date", "code", "earnings_surprise", "earnings_acceleration"]].sort_values(
        ["date", "code"]
    ).reset_index(drop=True)
