"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Base class for all trading strategies.

    Subclasses must define ``name`` and ``generate_signal``.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate_signal(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Generate trading signals.

        Parameters
        ----------
        data : DataFrame
            Market data (date, code, close, ...).
        factors : DataFrame, optional
            Pre-computed factors (date, code, rsi, obv, ...).

        Returns
        -------
        DataFrame
            Columns: date, code, signal (int: 1/-1/0), confidence (float).
        """
        ...
