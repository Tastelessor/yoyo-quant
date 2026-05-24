"""Position concentration limit rule."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.risk.rules import Rule, RuleContext


class PositionLimitRule(Rule):
    """Rule wrapper for apply_position_limit."""

    name = "position_limit"
    priority = 150

    def __init__(self, max_weight: float = 0.3):
        self.max_weight = max_weight

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.positions = apply_position_limit(ctx.positions, self.max_weight)
        return ctx


def apply_position_limit(
    positions: pd.DataFrame,
    max_weight: float = 0.3,
) -> pd.DataFrame:
    """Cap individual position weight and redistribute excess.

    For each date, any weight exceeding max_weight is capped.
    The excess is redistributed equally among uncapped positions
    so that total weight sums to 1.

    Parameters
    ----------
    positions : DataFrame
        Position data with columns: date, code, weight, shares.
    max_weight : float
        Maximum allowed weight per position (0-1).

    Returns
    -------
    DataFrame
        Adjusted position data with same columns.
    """
    if positions.empty:
        return positions.copy()

    chunks = []
    for _, group in positions.groupby("date"):
        chunk = group.copy()
        weights = chunk["weight"].values.copy()

        if max_weight <= 0:
            chunk["weight"] = 0.0
            chunk["shares"] = 0
            chunks.append(chunk)
            continue

        # Iteratively cap and redistribute until stable
        for _ in range(len(weights)):
            excess = np.maximum(weights - max_weight, 0)
            total_excess = excess.sum()
            if total_excess < 1e-10:
                break
            weights = np.minimum(weights, max_weight)
            uncapped = weights < max_weight - 1e-10
            if uncapped.any():
                weights[uncapped] += total_excess / uncapped.sum()
            else:
                # All capped — excess becomes cash, don't redistribute
                break

        chunk["weight"] = weights
        # Recalculate shares proportionally
        original_shares = chunk["shares"].values
        original_weights = group["weight"].values
        price_proxy = np.where(
            original_weights > 0, original_shares / original_weights, 0
        )
        new_shares = np.where(price_proxy > 0, weights * price_proxy, 0)
        chunk["shares"] = np.floor(new_shares / 100).astype(int) * 100

        chunks.append(chunk)

    return pd.concat(chunks, ignore_index=True)
