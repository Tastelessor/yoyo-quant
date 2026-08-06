"""Earnings factor functions.

These are passthrough functions — the actual computation
(PIT ranking, Z-Score standardization) happens in data/earnings.py.
The factor functions exist to maintain the registry interface contract:
def calc_xxx(df: pd.DataFrame) -> pd.Series.
"""

from __future__ import annotations

import pandas as pd


def calc_earnings_surprise(df: pd.DataFrame) -> pd.Series:
    """Passthrough: returns the pre-computed earnings_surprise column."""
    return df["earnings_surprise"]


def calc_earnings_acceleration(df: pd.DataFrame) -> pd.Series:
    """Passthrough: returns the pre-computed earnings_acceleration column."""
    return df["earnings_acceleration"]
