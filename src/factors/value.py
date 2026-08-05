"""Value factor functions: EP (Earnings-to-Price) and BP (Book-to-Price).

Uses reciprocal of PE/PB for linearity — PE=500 vs PE=1000 is virtually
identical in EP space but looks like a 2x gap in PE space.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_ep(df: pd.DataFrame) -> pd.Series:
    """Earnings-to-Price = 1/PE. PE<=0 or NaN → NaN."""
    df = _prepare(df)
    pe = df["pe"].astype(float)
    result = np.where(pe > 0, 1.0 / pe, np.nan)
    return pd.Series(result, index=df.index)


def calc_bp(df: pd.DataFrame) -> pd.Series:
    """Book-to-Price = 1/PB. PB<=0 or NaN → NaN."""
    df = _prepare(df)
    pb = df["pb"].astype(float)
    result = np.where(pb > 0, 1.0 / pb, np.nan)
    return pd.Series(result, index=df.index)
