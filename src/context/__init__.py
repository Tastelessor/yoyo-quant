"""Context layer: market regime detection, dynamic stock selection, and strategy routing."""

from src.context.regime import detect_regime
from src.context.regime_switch import RegimeSwitchStrategy
from src.context.stock_selector import (
    evaluate_factors,
    factor_coverage,
    factor_dispersion,
    rank_stability,
    select_tradable,
)

__all__ = [
    "RegimeSwitchStrategy",
    "detect_regime",
    "evaluate_factors",
    "factor_coverage",
    "factor_dispersion",
    "rank_stability",
    "select_tradable",
]
