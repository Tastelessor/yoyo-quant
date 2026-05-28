"""YAML config loader: load, validate, and build objects from config."""

from __future__ import annotations

import inspect
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


def build_industry_map(
    cfg: dict,
) -> tuple[dict[str, str], int] | None:
    """Build industry map from config.

    Returns ``(industry_map, min_peers)`` or ``None`` if neutralization
    is not enabled.
    """
    neu_cfg = cfg.get("neutralization")
    if not neu_cfg or not neu_cfg.get("enabled", False):
        return None
    from src.data.fetcher import fetch_all_stocks

    stocks_df = fetch_all_stocks()
    industry_map = dict(zip(stocks_df["code"], stocks_df["industry"]))
    min_peers = neu_cfg.get("min_peers", 3)
    return industry_map, min_peers


def _inject_neutralization(
    params: dict,
    industry_map_cfg: tuple[dict[str, str], int] | None,
    strategy_name: str,
) -> None:
    """Inject industry_map and min_peers into strategy params if supported."""
    if industry_map_cfg is None:
        return
    from src.strategies.registry import _REGISTRY

    im_dict, min_peers = industry_map_cfg
    strat_cls = _REGISTRY.get(strategy_name)
    if strat_cls and "industry_map" in inspect.signature(strat_cls.__init__).parameters:
        params["industry_map"] = im_dict
        params["min_peers"] = min_peers


def build_strategies(
    cfg: dict,
    industry_map_cfg: tuple[dict[str, str], int] | None = None,
) -> Strategy | WeightedVoteCombiner | FilterCombiner:
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
        params = dict(r.get("params") or {})
        _inject_neutralization(params, industry_map_cfg, r["name"])
        strat = get_strategy(r["name"], **params)
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


def build_backtest_config(cfg: dict) -> dict:
    """Extract backtest engine parameters from config.

    Config format::

        backtest:
            stop_loss: -0.15
            take_profit: 0.05
            atr_stop_loss:
                atr_multiplier: 3.0
                atr_window: 14

    Returns
    -------
    dict
        Keys: stop_loss, take_profit, atr_stop_loss (all optional).
    """
    bt_cfg = cfg.get("backtest", {})
    result = {}
    if "stop_loss" in bt_cfg:
        result["stop_loss"] = bt_cfg["stop_loss"]
    if "take_profit" in bt_cfg:
        result["take_profit"] = bt_cfg["take_profit"]
    if "atr_stop_loss" in bt_cfg:
        result["atr_stop_loss"] = bt_cfg["atr_stop_loss"]
    if "trading_cost" in bt_cfg:
        from src.backtest.engine import TradingCost

        result["trading_cost"] = TradingCost(**bt_cfg["trading_cost"])
    return result


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


def build_stock_selector(cfg: dict):
    """Build stock selector callable from config.

    Reads the ``stock_selector`` section and returns a callable
    that wraps ``select_tradable`` with the configured parameters.

    Parameters
    ----------
    cfg : dict
        Full config dict containing a ``stock_selector`` section.

    Returns
    -------
    callable or None
        ``(factor_df) -> dict[pd.Timestamp, list[str]]``
        Returns None if no ``stock_selector`` section exists or
        ``factors`` list is empty/missing.
    """
    ss_cfg = cfg.get("stock_selector")
    if ss_cfg is None:
        return None

    factor_names = ss_cfg.get("factors")
    if not factor_names:
        return None

    params = {
        "lookback": ss_cfg.get("lookback", 60),
        "lag": ss_cfg.get("lag", 5),
        "min_coverage": ss_cfg.get("min_coverage", 0.8),
        "min_stability": ss_cfg.get("min_stability", 0.3),
        "min_dispersion": ss_cfg.get("min_dispersion", 0.10),
        "min_stocks": ss_cfg.get("min_stocks", 5),
        "top_n": ss_cfg.get("top_n"),
        "min_pass_count": ss_cfg.get("min_pass_count", 1),
    }

    from src.context.stock_selector import select_tradable

    def selector(factor_df):
        return select_tradable(factor_df, factor_names, **params)

    return selector


def build_regime_switch(
    cfg: dict,
    industry_map_cfg: tuple[dict[str, str], int] | None = None,
):
    """Build RegimeSwitchStrategy from config.

    Config format::

        strategies:
            regime_switch:
                regimes:
                    trend_up:
                        name: momentum_breakout
                        params: { vol_window: 20 }
                        factor_weights: data/audit/trend_up_weights.parquet
                    trend_down:
                        name: rsi_reversal
                        params: { window: 14 }
                    range:
                        name: mean_reversion
                        params: { window: 20 }
                        factor_weights: { money_flow_6d: 0.6, obv_6d: 0.4 }
                    volatile:
                        name: gtja_volume_price
                        params: { rebalance: 20, top_n: 5, bottom_n: 3 }
                        factor_weights: data/audit/volatile_weights.parquet

    ``factor_weights`` is optional. It can be:
    - A file path (str): parquet with columns [name, weight]
    - An inline dict: {factor_name: weight, ...}

    Returns RegimeSwitchStrategy if regime_switch section exists, else None.
    """
    import pandas as pd

    rs_cfg = cfg.get("strategies", cfg).get("regime_switch")
    if rs_cfg is None:
        return None

    from src.context.regime_switch import RegimeSwitchStrategy

    regimes = {}
    for regime_label, strat_cfg in rs_cfg["regimes"].items():
        params = dict(strat_cfg.get("params") or {})
        _inject_neutralization(params, industry_map_cfg, strat_cfg["name"])
        fw = strat_cfg.get("factor_weights")

        if fw is not None:
            if isinstance(fw, str):
                fw_path = Path(fw)
                if not fw_path.exists():
                    raise FileNotFoundError(
                        f"Factor weights file not found: {fw_path.resolve()}"
                    )
                weights_df = pd.read_parquet(fw)
                if not {"name", "weight"}.issubset(weights_df.columns):
                    raise ValueError(
                        f"Factor weights parquet must have 'name' and 'weight' "
                        f"columns, got: {list(weights_df.columns)}"
                    )
                params["weights"] = dict(zip(weights_df["name"], weights_df["weight"]))
            elif isinstance(fw, dict):
                params["weights"] = fw

        regimes[regime_label] = get_strategy(strat_cfg["name"], **params)
    return RegimeSwitchStrategy(regimes=regimes)


def build_combined_strategy(cfg: dict) -> dict:
    """Build combined market regime + stock strategy from config.

    Handles the optional ``strategies.market_regime`` section and the
    ``strategies.regime_switch`` path (production).  When
    ``regime_switch`` is present, it takes priority over ``rules``.

    Returns
    -------
    dict
        ``{"regime": MarketRegime | None, "strategy": Strategy | Combiner}``
    """
    from src.strategies.builtin.market_regime import MarketRegime

    industry_map_cfg = build_industry_map(cfg)

    strategies_cfg = cfg.get("strategies", cfg)
    regime_cfg = strategies_cfg.get("market_regime")

    regime = None
    if regime_cfg is not None:
        regime = MarketRegime(
            ma_short=regime_cfg.get("ma_short", 50),
            ma_long=regime_cfg.get("ma_long", 200),
            exposure=regime_cfg.get("exposure"),
        )

    # Try regime_switch path first (production), then rules fallback
    rs = build_regime_switch(strategies_cfg, industry_map_cfg=industry_map_cfg)
    if rs is not None:
        strategy = rs
    else:
        strategy = build_strategies(strategies_cfg, industry_map_cfg=industry_map_cfg)

    return {"regime": regime, "strategy": strategy}
