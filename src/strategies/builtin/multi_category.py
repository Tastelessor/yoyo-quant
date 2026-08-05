"""Multi-category strategy: combine signals from multiple factor categories."""

from __future__ import annotations

import pandas as pd

from strategies.base import Strategy
from strategies.combiner import WeightedVoteCombiner
from strategies.registry import get_strategy, register_strategy


@register_strategy("multi_category")
class MultiCategoryStrategy(Strategy):
    """Combine signals from multiple factor category strategies via weighted voting.

    Each category (momentum, mean_reversion, etc.) is an independent alpha source.
    Low-correlation signals are combined to improve risk-adjusted returns.

    Parameters
    ----------
    categories : list[dict]
        Each dict has ``name`` (registered strategy name), ``weight`` (float),
        and optional ``params`` (dict passed to the strategy constructor).
    threshold : float
        Weighted vote threshold for signal generation (default 0.0).
    """

    name = "multi_category"

    def __init__(
        self,
        categories: list[dict],
        threshold: float = 0.0,
    ):
        if not categories:
            raise ValueError("MultiCategoryStrategy requires at least one category")

        self.categories = categories
        self.threshold = threshold

        # Build sub-strategies
        strategies: list[tuple[Strategy, float]] = []
        for cat in categories:
            strat = get_strategy(cat["name"], **(cat.get("params") or {}))
            weight = cat.get("weight", 1.0)
            strategies.append((strat, weight))

        self._combiner = WeightedVoteCombiner(
            strategies=strategies,
            threshold=threshold,
        )

    def generate_signal(
        self,
        data: pd.DataFrame,
        factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Generate combined signals from all category strategies."""
        return self._combiner.combine(data, factors=factors)
