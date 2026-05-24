"""Context layer: market regime detection and dynamic strategy routing."""

from src.context.regime import detect_regime
from src.context.regime_switch import RegimeSwitchStrategy

__all__ = ["RegimeSwitchStrategy", "detect_regime"]
