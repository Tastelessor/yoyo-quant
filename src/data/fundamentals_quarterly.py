"""Point-in-Time quarterly financial indicator pipeline.

Fetches fina_indicator from tushare (ROE, margins, debt ratios, OCF per share),
builds a daily panel with PIT alignment via merge_asof backward.
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


def _to_ts_code(code: str) -> str:
    """Convert 6-digit code to tushare format."""
    if code.startswith("6"):
        return f"{code}.SH"
    return f"{code}.SZ"


def fetch_fina_indicator(
    ts_code: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Fetch quarterly financial indicators for a single stock from tushare.

    Parameters
    ----------
    ts_code : str
        Stock code (6-digit or tushare format).
    cache_dir : Path | str | None
        Cache directory. Defaults to data/raw/fundamentals_quarterly/.

    Returns
    -------
    DataFrame
        Columns: code, ann_date, end_date, roe, ocfps.
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "raw"
            / "fundamentals_quarterly"
        )
    else:
        cache_dir = Path(cache_dir)

    code = ts_code.split(".")[0] if "." in ts_code else ts_code
    cache_file = cache_dir / f"{code}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_fmt = _to_ts_code(code) if "." not in ts_code else ts_code
    raw = api.fina_indicator(
        ts_code=ts_fmt,
        fields="ts_code,ann_date,end_date,roe,ocfps",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["code", "ann_date", "end_date", "roe", "ocfps"]
        )

    df = raw.rename(columns={"ts_code": "code"})
    df["code"] = df["code"].str.split(".").str[0]
    df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")
    df["roe"] = pd.to_numeric(df["roe"], errors="coerce")
    df["ocfps"] = pd.to_numeric(df["ocfps"], errors="coerce")

    result = df[["code", "ann_date", "end_date", "roe", "ocfps"]].copy()
    cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_file, index=False)
    return result


def fetch_fina_batch(
    codes: list[str],
    cache_dir: Path | str | None = None,
    sleep_sec: float = 0.5,
    progress: bool = True,
) -> pd.DataFrame:
    """Fetch quarterly financial indicators for a list of stock codes.

    Parameters
    ----------
    codes : list[str]
        Stock codes (6-digit, e.g. ["000001", "600519"]).
    cache_dir : Path | str | None
        Cache directory. Defaults to data/raw/fundamentals_quarterly/.
    sleep_sec : float
        Sleep between API calls for rate limiting.
    progress : bool
        Whether to log progress.

    Returns
    -------
    DataFrame
        Columns: code, ann_date, end_date, roe, ocfps.
    """
    import time

    if cache_dir is None:
        cache_dir = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "raw"
            / "fundamentals_quarterly"
        )
    else:
        cache_dir = Path(cache_dir)

    cache_file = cache_dir / f"all_fina_{'_'.join(sorted(codes)[:5])}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    all_frames = []

    for i, code in enumerate(codes):
        try:
            df = fetch_fina_indicator(code, cache_dir=cache_dir)
            if len(df) > 0:
                all_frames.append(df)
        except Exception as e:
            logger.warning("Failed to fetch fina_indicator for %s: %s", code, e)

        if sleep_sec > 0:
            time.sleep(sleep_sec)

        if progress and (i + 1) % 20 == 0:
            logger.info("Fetched fina_indicator for %d / %d stocks", i + 1, len(codes))

    if not all_frames:
        return pd.DataFrame(
            columns=["code", "ann_date", "end_date", "roe", "ocfps"]
        )

    result = pd.concat(all_frames, ignore_index=True)
    result = result.sort_values(["code", "ann_date"]).reset_index(drop=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_file, index=False)
    return result


def build_quality_panel(
    fina_df: pd.DataFrame,
    trade_dates: pd.DatetimeIndex,
    codes: list[str],
) -> pd.DataFrame:
    """Build daily quality panel with PIT alignment and Z-Score standardization.

    Pipeline:
    1. Sort by (ann_date, end_date) so newer quarters win on same-day collision
    2. merge_asof backward to daily panel (PIT: use ann_date, not end_date)
    3. Compute roe_stability: rolling 8-quarter std of ROE, negated
    4. Daily cross-sectional Z-Score standardization, clip [-3, 3]

    Returns
    -------
    DataFrame
        Columns: date, code, roe_level, roe_stability, cashflow_quality.
    """
    if fina_df.empty:
        grid = pd.MultiIndex.from_product(
            [trade_dates, codes], names=["date", "code"]
        ).to_frame(index=False)
        grid["roe_level"] = np.nan
        grid["roe_stability"] = np.nan
        grid["cashflow_quality"] = np.nan
        return grid.sort_values(["date", "code"]).reset_index(drop=True)

    df = fina_df.copy()
    df["code"] = df["code"].astype(str)
    df["ann_date"] = pd.to_datetime(df["ann_date"]).astype("datetime64[ns]")

    # Step 1: Sort so newer end_date wins on same ann_date
    df = df.sort_values(["code", "ann_date", "end_date"]).reset_index(drop=True)

    # Step 2: Compute roe_stability per stock (rolling 8-quarter std)
    df["roe_stability"] = (
        df.groupby("code")["roe"]
        .transform(lambda s: -s.rolling(8, min_periods=2).std())
    )

    # Step 3: Prepare events for merge_asof
    events = df[["ann_date", "code", "roe", "roe_stability", "ocfps"]].copy()
    events = events.rename(
        columns={
            "ann_date": "date",
            "roe": "roe_level",
            "ocfps": "cashflow_quality",
        }
    )
    events["code"] = events["code"].astype(str)
    events["date"] = pd.to_datetime(events["date"]).astype("datetime64[ns]")

    # Step 4: Build daily grid and merge
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
    for col in ["roe_level", "roe_stability", "cashflow_quality"]:
        raw = panel[col].copy()
        non_nan_count = panel.groupby("date")[col].transform("count")
        means = panel.groupby("date")[col].transform("mean")
        stds = panel.groupby("date")[col].transform("std")

        do_zscore = (non_nan_count >= 2) & (stds > 0)
        z = np.where(
            do_zscore,
            np.clip((panel[col] - means) / stds, -3.0, 3.0),
            panel[col],
        )
        z = pd.Series(z, index=panel.index)
        # Where raw data exists but Z-Score is NaN (single stock on date) → fill 0.0
        # Where raw data is NaN (before any announcement) → keep NaN
        z = z.mask(raw.notna() & z.isna(), 0.0)
        panel[col] = z

    return (
        panel[["date", "code", "roe_level", "roe_stability", "cashflow_quality"]]
        .sort_values(["date", "code"])
        .reset_index(drop=True)
    )
