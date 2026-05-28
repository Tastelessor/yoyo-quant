"""Drawdown circuit breaker for portfolio exposure control.

Monitors portfolio equity curve and compresses exposure when drawdown
exceeds a threshold. Designed as an asymmetric risk overlay:
normal markets get full exposure, only crisis drawdowns trigger compression.

Features:
- Hysteresis: recovery threshold shallower than trigger threshold
- Dead-zone: only adjusts exposure when change exceeds step size
- Fast recovery: momentum-based quench bypasses slow hysteresis
"""

from __future__ import annotations

import pandas as pd


class DrawdownCircuitBreaker:
    """Asymmetric drawdown-based exposure scaler.

    Parameters
    ----------
    threshold : float
        Drawdown level that triggers compression (e.g. -0.15 = -15%).
        Must be negative.
    recovery_threshold : float
        Drawdown level at which exposure begins recovering (e.g. -0.03).
        Must be shallower (less negative) than threshold.
    min_exposure : float
        Minimum exposure when fully compressed (e.g. 0.1 = 10%).
    ramp_speed : float
        Controls how quickly exposure recovers between min_exposure and 1.0.
        Higher = faster recovery. Default 2.0.
    dead_zone : float
        Minimum exposure change to trigger position adjustment (e.g. 0.05).
        Reduces unnecessary daily micro-adjustments. Default 0.05.
    fast_recovery_momentum : float
        3-day equity return threshold to trigger fast recovery (e.g. 0.05 = 5%).
        When exceeded, exposure snaps to 1.0 bypassing hysteresis. Default 0.05.
    fast_recovery_window : int
        Number of days to look back for momentum calculation. Default 3.
    """

    def __init__(
        self,
        threshold: float = -0.15,
        recovery_threshold: float = -0.05,
        min_exposure: float = 0.1,
        ramp_speed: float = 2.0,
        dead_zone: float = 0.05,
        fast_recovery_momentum: float = 0.05,
        fast_recovery_window: int = 3,
    ):
        if threshold >= 0:
            raise ValueError("threshold must be negative")
        if recovery_threshold <= threshold:
            raise ValueError("recovery_threshold must be shallower than threshold")
        if not 0 <= min_exposure <= 1:
            raise ValueError("min_exposure must be in [0, 1]")

        self.threshold = threshold
        self.recovery_threshold = recovery_threshold
        self.min_exposure = min_exposure
        self.ramp_speed = ramp_speed
        self.dead_zone = dead_zone
        self.fast_recovery_momentum = fast_recovery_momentum
        self.fast_recovery_window = fast_recovery_window

        self._peak: float = 0.0
        self._last_drawdown: float = 0.0
        self._current_exposure: float = 1.0

    def _drawdown_to_exposure(self, drawdown: float) -> float:
        """Map a drawdown value to exposure level."""
        if drawdown >= self.recovery_threshold:
            return 1.0
        if drawdown <= self.threshold:
            return self.min_exposure
        span = self.recovery_threshold - self.threshold
        if span <= 0:
            return self.min_exposure
        fraction = (drawdown - self.threshold) / span
        return self.min_exposure + (1.0 - self.min_exposure) * (fraction ** self.ramp_speed)

    def compute_exposure(self, equity: pd.Series) -> pd.Series:
        """Compute daily exposure from equity curve with dead-zone filtering.

        Parameters
        ----------
        equity : Series
            Portfolio equity indexed by date.

        Returns
        -------
        Series
            Exposure fraction per date, values in [min_exposure, 1.0].
        """
        if equity.empty:
            return pd.Series(dtype=float)

        exposure_values = []
        for val in equity.values:
            if val > self._peak:
                self._peak = val

            if self._peak <= 0:
                exposure_values.append(1.0)
                continue

            self._last_drawdown = (val - self._peak) / self._peak
            raw_exposure = self._drawdown_to_exposure(self._last_drawdown)

            # Dead-zone: only update if change exceeds step
            if abs(raw_exposure - self._current_exposure) > self.dead_zone:
                self._current_exposure = raw_exposure

            exposure_values.append(self._current_exposure)

        return pd.Series(exposure_values, index=equity.index, dtype=float)

    def check_fast_recovery(self, equity_history: list[float]) -> bool:
        """Check if recent equity momentum triggers fast recovery.

        Parameters
        ----------
        equity_history : list of float
            Recent daily equity values (most recent last).

        Returns
        -------
        bool
            True if fast recovery should be triggered.
        """
        if len(equity_history) < self.fast_recovery_window + 1:
            return False
        recent = equity_history[-(self.fast_recovery_window + 1):]
        if recent[0] <= 0:
            return False
        momentum = (recent[-1] - recent[0]) / recent[0]
        return momentum > self.fast_recovery_momentum

    def update_equity(self, equity: pd.Series) -> None:
        """Update internal state from equity curve."""
        if equity.empty:
            return
        peak = equity.max()
        if peak > self._peak:
            self._peak = peak
        if self._peak > 0:
            self._last_drawdown = (equity.iloc[-1] - self._peak) / self._peak

    def exposure_fn(self) -> callable:
        """Create an exposure_fn compatible with walk_forward_backtest."""
        def _fn(dates: pd.DatetimeIndex) -> pd.Series:
            if self._peak <= 0:
                return pd.Series(1.0, index=dates, dtype=float)
            exp = self._drawdown_to_exposure(self._last_drawdown)
            return pd.Series(exp, index=dates, dtype=float)
        return _fn

    def reset(self) -> None:
        """Reset internal state."""
        self._peak = 0.0
        self._last_drawdown = 0.0
        self._current_exposure = 1.0
