"""YAML config loader: load, validate, and build objects from config."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.risk.rule_engine import RuleEngine
from src.risk.rule_registry import get_risk_rule
from src.strategies.base import Strategy
from src.strategies.combiner import FilterCombiner, WeightedVoteCombiner
from src.strategies.registry import get_strategy


def load_config(path: Path) -> dict:
    """Load a YAML config file and validate required sections."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path) as f:
        cfg = yaml.safe_load(f)

    if "strategies" not in cfg:
        raise ValueError("Config missing required section: 'strategies'")
    if "risk" not in cfg:
        raise ValueError("Config missing required section: 'risk'")

    return cfg


def build_strategies(cfg: dict) -> Strategy | WeightedVoteCombiner | FilterCombiner:
    """Build strategy or combiner from config.

    Config format::

        combiner:
            type: weighted_vote | filter
            threshold: 0.0
        rules:
            - name: strategy_name
              params: { ... }
              weight: 0.5
    """
    rules_cfg = cfg["rules"]
    if not rules_cfg:
        raise ValueError("At least one strategy rule is required")

    strategies = []
    for r in rules_cfg:
        strat = get_strategy(r["name"], **(r.get("params") or {}))
        weight = r.get("weight", 1.0)
        strategies.append((strat, weight))

    combiner_cfg = cfg.get("combiner")
    if combiner_cfg is None or len(strategies) == 1:
        # No combiner or single strategy → return the strategy directly
        return strategies[0][0]

    ctype = combiner_cfg["type"]
    if ctype == "weighted_vote":
        return WeightedVoteCombiner(
            strategies=strategies,
            threshold=combiner_cfg.get("threshold", 0.0),
        )
    elif ctype == "filter":
        if len(strategies) < 2:
            raise ValueError("FilterCombiner needs at least 2 strategies")
        return FilterCombiner(
            primary=strategies[0][0],
            filters=[s for s, _ in strategies[1:]],
        )
    else:
        raise ValueError(f"Unknown combiner type: {ctype!r}")


def build_risk_engine(cfg: dict) -> RuleEngine:
    """Build RuleEngine from config.

    Config format::

        rules:
            - name: rule_name
              params: { ... }
    """
    rules_cfg = cfg.get("rules", [])
    rules = []
    for r in rules_cfg:
        params = r.get("params") or {}
        rules.append(get_risk_rule(r["name"], **params))
    return RuleEngine(rules)


def build_combined_strategy(cfg: dict) -> dict:
    """Build combined market regime + stock strategy from config.

    Handles the optional ``strategies.market_regime`` section.

    Config format::

        strategies:
            market_regime:
                ma_short: 50
                ma_long: 200
                exposure: { bullish: 1.0, neutral: 0.6, ... }
            combiner:
                type: weighted_vote
            rules:
                - name: multifactor
                  params: { top_n: 5 }

    Returns
    -------
    dict
        ``{"regime": MarketRegime | None, "strategy": Strategy | Combiner}``
    """
    from src.strategies.builtin.market_regime import MarketRegime

    strategies_cfg = cfg.get("strategies", cfg)
    regime_cfg = strategies_cfg.get("market_regime")

    regime = None
    if regime_cfg is not None:
        regime = MarketRegime(
            ma_short=regime_cfg.get("ma_short", 50),
            ma_long=regime_cfg.get("ma_long", 200),
            exposure=regime_cfg.get("exposure"),
        )

    strategy = build_strategies(strategies_cfg)

    return {"regime": regime, "strategy": strategy}
