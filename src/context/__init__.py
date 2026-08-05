"""Context layer: regime detection, strategy routing, stock selection, parameter routing."""

from context.param_router import route_params
from context.regime import detect_regime
from context.regime_switch import RegimeSwitchStrategy
from context.stock_selector import (
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
