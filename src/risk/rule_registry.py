"""Risk rule registry: map rule names to their classes."""

from __future__ import annotations

from typing import Any

from src.risk.rules import Rule

_RISK_RULES: dict[str, type[Rule]] = {}


def register_risk_rule(name: str, cls: type[Rule]) -> None:
    _RISK_RULES[name] = cls


def get_risk_rule(name: str, **params: Any) -> Rule:
    if name not in _RISK_RULES:
        raise KeyError(f"Unknown risk rule: {name!r}")
    return _RISK_RULES[name](**params)


def list_risk_rules() -> list[str]:
    return list(_RISK_RULES.keys())


# Auto-register built-in rules
def _register_defaults() -> None:
    from src.risk.position_limit import PositionLimitRule
    from src.risk.stop_loss import ATRStopLossRule, FixedStopLossRule
    from src.risk.tradability import T1Rule, TradabilityRule

    register_risk_rule("fixed_stop_loss", FixedStopLossRule)
    register_risk_rule("atr_stop_loss", ATRStopLossRule)
    register_risk_rule("position_limit", PositionLimitRule)
    register_risk_rule("tradability", TradabilityRule)
    register_risk_rule("t1", T1Rule)


_register_defaults()
