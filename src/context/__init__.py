"""Context layer: regime detection, strategy routing, stock selection, parameter routing."""

from src.context.param_router import route_params
from src.context.regime import detect_regime
from src.context.regime_switch import RegimeSwitchStrategy
from src.context.stock_selector import (
    evaluate_factors,
    evaluate_factors_by_regime,
    factor_coverage,
    factor_dispersion,
    rank_stability,
    select_tradable,
)

__all__ = [
    "RegimeSwitchStrategy",
    "detect_regime",
    "evaluate_factors",
    "evaluate_factors_by_regime",
    "factor_coverage",
    "factor_dispersion",
    "rank_stability",
    "route_params",
    "select_tradable",
]
