"""Quality factor functions.

These are passthrough functions — the actual computation
(PIT alignment, ROE stability, Z-Score standardization)
happens in data/fundamentals_quarterly.py.
The factor functions exist to maintain the registry interface contract:
def calc_xxx(df: pd.DataFrame) -> pd.Series.
"""

from __future__ import annotations

import pandas as pd


def calc_roe_level(df: pd.DataFrame) -> pd.Series:
    """Passthrough: returns the pre-computed roe_level column."""
    return df["roe_level"]


def calc_roe_stability(df: pd.DataFrame) -> pd.Series:
    """Passthrough: returns the pre-computed roe_stability column."""
    return df["roe_stability"]


def calc_cashflow_quality(df: pd.DataFrame) -> pd.Series:
    """Passthrough: returns the pre-computed cashflow_quality column."""
    return df["cashflow_quality"]
