"""Stop loss rules: fixed percentage and ATR-based dynamic stop."""

from __future__ import annotations

import pandas as pd

from src.factors.volume_price import calc_atr
from src.risk.rules import Rule, RuleContext


def _get_current_prices(
    positions: pd.DataFrame, market_data: pd.DataFrame,
) -> pd.Series:
    """Look up the close price for each position row from market_data."""
    if positions.empty:
        return pd.Series(dtype=float)

    merged = positions.merge(
        market_data[["date", "code", "close"]],
        on=["date", "code"],
        how="left",
    )
    return merged["close"]


class FixedStopLossRule(Rule):
    """Stop loss at a fixed percentage below average cost.

    Parameters
    ----------
    threshold : float
        Loss fraction that triggers a stop (e.g. -0.08 for 8%).
        Must be negative.
    """

    name = "fixed_stop_loss"
    priority = 120

    def __init__(self, threshold: float = -0.08):
        self.threshold = threshold

    def apply(self, ctx: RuleContext) -> RuleContext:
        if ctx.positions.empty or "avg_cost" not in ctx.positions.columns:
            return ctx

        ctx.positions = ctx.positions.copy()
        prices = _get_current_prices(ctx.positions, ctx.market_data)
        avg_cost = ctx.positions["avg_cost"]
        pnl_pct = (prices - avg_cost) / avg_cost

        stopped = pnl_pct < self.threshold
        if stopped.any():
            ctx.positions.loc[stopped, "weight"] = 0.0
            ctx.positions.loc[stopped, "shares"] = 0
            ctx.metadata["stopped_out"] = (
                ctx.positions.loc[stopped, "code"].tolist()
            )

        return ctx


class ATRStopLossRule(Rule):
    """Dynamic stop loss based on Average True Range.

    Stop price = avg_cost - atr_multiplier * ATR.
    Position is closed when current price < stop price.

    Parameters
    ----------
    atr_multiplier : float
        How many ATRs below avg_cost to set the stop.
    atr_window : int
        Rolling window for ATR calculation.
    """

    name = "atr_stop_loss"
    priority = 121

    def __init__(self, atr_multiplier: float = 3.0, atr_window: int = 14):
        self.atr_multiplier = atr_multiplier
        self.atr_window = atr_window

    def apply(self, ctx: RuleContext) -> RuleContext:
        if ctx.positions.empty or "avg_cost" not in ctx.positions.columns:
            return ctx

        ctx.positions = ctx.positions.copy()
        stopped_codes = []
        for idx, row in ctx.positions.iterrows():
            code = row["code"]
            date = row["date"]
            avg_cost = row["avg_cost"]

            # Get historical data up to current date for this stock
            hist = ctx.market_data[
                (ctx.market_data["code"] == code)
                & (ctx.market_data["date"] <= date)
            ].sort_values("date")

            if len(hist) < self.atr_window:
                continue

            atr_series = calc_atr(hist, window=self.atr_window)
            current_atr = atr_series.iloc[-1]

            if pd.isna(current_atr):
                continue

            stop_price = avg_cost - self.atr_multiplier * current_atr
            current_price = hist["close"].iloc[-1]

            if current_price < stop_price:
                ctx.positions.at[idx, "weight"] = 0.0
                ctx.positions.at[idx, "shares"] = 0
                stopped_codes.append(code)

        if stopped_codes:
            ctx.metadata["stopped_out"] = stopped_codes

        return ctx
