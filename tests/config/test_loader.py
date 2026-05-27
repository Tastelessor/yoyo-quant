"""Config loader tests."""

import tempfile
from pathlib import Path

import pytest
import yaml

import pandas as pd

from src.config.loader import (
    build_regime_switch,
    build_risk_engine,
    build_stock_selector,
    build_strategies,
    load_config,
)
from src.risk.rule_engine import RuleEngine
from src.strategies.base import Strategy
from src.strategies.combiner import WeightedVoteCombiner


@pytest.fixture
def valid_config():
    return {
        "portfolio": {"allocator": "equal_weight", "capital": 1_000_000},
        "strategies": {
            "combiner": {"type": "weighted_vote", "threshold": 0.0},
            "rules": [
                {"name": "mean_reversion", "params": {"window": 20, "num_std": 2.0}, "weight": 0.5},
                {"name": "rsi_reversal", "params": {"window": 14, "oversold": 30, "overbought": 70}, "weight": 0.5},
            ],
        },
        "risk": {
            "rules": [
                {"name": "fixed_stop_loss", "params": {"threshold": -0.08}},
                {"name": "position_limit", "params": {"max_weight": 0.3}},
                {"name": "tradability"},
                {"name": "t1"},
            ],
        },
    }


@pytest.fixture
def valid_yaml_file(valid_config):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(valid_config, f)
        f.flush()
        yield Path(f.name)


class TestLoadConfig:
    def test_load_valid_yaml(self, valid_yaml_file):
        cfg = load_config(valid_yaml_file)
        assert cfg["portfolio"]["capital"] == 1_000_000
        assert len(cfg["strategies"]["rules"]) == 2
        assert len(cfg["risk"]["rules"]) == 4

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))

    def test_missing_strategies_section(self):
        cfg = {"portfolio": {}, "risk": {"rules": []}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(cfg, f)
            f.flush()
            with pytest.raises(ValueError, match="strategies"):
                load_config(Path(f.name))

    def test_missing_risk_section(self):
        cfg = {"portfolio": {}, "strategies": {"combiner": {"type": "weighted_vote"}, "rules": []}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(cfg, f)
            f.flush()
            with pytest.raises(ValueError, match="risk"):
                load_config(Path(f.name))


class TestBuildStrategies:
    def test_builds_combiner(self, valid_config):
        result = build_strategies(valid_config["strategies"])
        assert isinstance(result, WeightedVoteCombiner)

    def test_unknown_strategy_raises(self):
        cfg = {
            "combiner": {"type": "weighted_vote"},
            "rules": [{"name": "nonexistent_strategy", "params": {}, "weight": 1.0}],
        }
        with pytest.raises(KeyError, match="nonexistent_strategy"):
            build_strategies(cfg)

    def test_single_strategy_no_combiner(self):
        cfg = {
            "rules": [{"name": "mean_reversion", "params": {"window": 20}, "weight": 1.0}],
        }
        result = build_strategies(cfg)
        assert isinstance(result, Strategy)

    def test_invalid_combiner_type(self):
        cfg = {
            "combiner": {"type": "invalid_type"},
            "rules": [
                {"name": "mean_reversion", "params": {}, "weight": 0.5},
                {"name": "rsi_reversal", "params": {}, "weight": 0.5},
            ],
        }
        with pytest.raises(ValueError, match="combiner"):
            build_strategies(cfg)


class TestBuildRiskEngine:
    def test_builds_engine(self, valid_config):
        result = build_risk_engine(valid_config["risk"])
        assert isinstance(result, RuleEngine)
        assert len(result.rules) == 4

    def test_rules_sorted_by_priority(self, valid_config):
        engine = build_risk_engine(valid_config["risk"])
        priorities = [r.priority for r in engine.rules]
        assert priorities == sorted(priorities)

    def test_unknown_rule_raises(self):
        cfg = {"rules": [{"name": "unknown_rule"}]}
        with pytest.raises(KeyError, match="unknown_rule"):
            build_risk_engine(cfg)

    def test_rules_without_params(self):
        cfg = {"rules": [{"name": "tradability"}, {"name": "t1"}]}
        engine = build_risk_engine(cfg)
        assert len(engine.rules) == 2


class TestBuildRegimeSwitch:
    """Tests for build_regime_switch with optional factor_weights."""

    def test_returns_none_when_no_regime_switch_section(self):
        cfg = {"strategies": {"combiner": {"type": "weighted_vote"}, "rules": []}}
        assert build_regime_switch(cfg) is None

    def test_builds_regime_switch_without_factor_weights(self):
        """Backward compat: no factor_weights key → strategy uses defaults."""
        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "trend_up": {
                            "name": "gtja_momentum",
                            "params": {"rebalance": 20, "top_n": 5, "bottom_n": 3},
                        },
                    }
                }
            }
        }
        rs = build_regime_switch(cfg)
        assert rs is not None
        assert "trend_up" in rs.regimes

    def test_inline_dict_factor_weights_injected(self):
        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "trend_up": {
                            "name": "gtja_volume_price",
                            "params": {"rebalance": 10, "top_n": 3, "bottom_n": 2},
                            "factor_weights": {"money_flow_6d": 0.6, "obv_6d": 0.4},
                        },
                    }
                }
            }
        }
        rs = build_regime_switch(cfg)
        strat = rs.regimes["trend_up"]
        assert strat.weights["money_flow_6d"] == 0.6
        assert strat.weights["obv_6d"] == 0.4

    def test_parquet_factor_weights_loaded(self, tmp_path):
        wf = pd.DataFrame({"name": ["money_flow_6d", "obv_6d"], "weight": [0.7, 0.3]})
        path = tmp_path / "weights.parquet"
        wf.to_parquet(path)

        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "range": {
                            "name": "gtja_volume_price",
                            "params": {"rebalance": 5},
                            "factor_weights": str(path),
                        },
                    }
                }
            }
        }
        rs = build_regime_switch(cfg)
        strat = rs.regimes["range"]
        assert strat.weights["money_flow_6d"] == 0.7
        assert strat.weights["obv_6d"] == 0.3

    def test_missing_parquet_file_raises(self):
        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "trend_up": {
                            "name": "gtja_volume_price",
                            "params": {},
                            "factor_weights": "/nonexistent/weights.parquet",
                        },
                    }
                }
            }
        }
        with pytest.raises(FileNotFoundError, match="Factor weights file not found"):
            build_regime_switch(cfg)

    def test_wrong_parquet_columns_raises(self, tmp_path):
        wf = pd.DataFrame({"factor_name": ["a"], "w": [0.5]})
        path = tmp_path / "bad.parquet"
        wf.to_parquet(path)

        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "range": {
                            "name": "gtja_volume_price",
                            "params": {},
                            "factor_weights": str(path),
                        },
                    }
                }
            }
        }
        with pytest.raises(ValueError, match="name.*weight.*columns"):
            build_regime_switch(cfg)

    def test_empty_factor_weights_dict(self):
        """Empty dict → treated as no weights (strategy uses defaults)."""
        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "range": {
                            "name": "gtja_volume_price",
                            "params": {},
                            "factor_weights": {},
                        },
                    }
                }
            }
        }
        rs = build_regime_switch(cfg)
        # Strategy uses DEFAULT_WEIGHTS when weights={} (falsy)
        assert rs.regimes["range"].weights["money_flow_6d"] > 0

    def test_multiple_regimes_each_own_weights(self):
        cfg = {
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "trend_up": {
                            "name": "gtja_volume_price",
                            "params": {},
                            "factor_weights": {"money_flow_6d": 0.9},
                        },
                        "range": {
                            "name": "gtja_volume_price",
                            "params": {},
                            "factor_weights": {"obv_6d": 0.8},
                        },
                    }
                }
            }
        }
        rs = build_regime_switch(cfg)
        assert rs.regimes["trend_up"].weights == {"money_flow_6d": 0.9}
        assert rs.regimes["range"].weights == {"obv_6d": 0.8}


class TestBuildStockSelector:
    """Tests for build_stock_selector config loader."""

    def test_returns_callable_when_section_exists(self):
        cfg = {
            "stock_selector": {
                "factors": ["calc_money_flow_6d", "calc_obv_6d"],
                "lookback": 60,
                "top_n": 50,
            }
        }
        fn = build_stock_selector(cfg)
        assert callable(fn)

    def test_returns_none_when_no_section(self):
        cfg = {"strategies": {"rules": []}}
        assert build_stock_selector(cfg) is None

    def test_returns_none_when_empty_factors(self):
        cfg = {"stock_selector": {"factors": []}}
        assert build_stock_selector(cfg) is None

    def test_returns_none_when_factors_missing(self):
        cfg = {"stock_selector": {"lookback": 60}}
        assert build_stock_selector(cfg) is None

    def test_uses_default_params_when_optional_keys_missing(self):
        cfg = {"stock_selector": {"factors": ["calc_money_flow_6d"]}}
        fn = build_stock_selector(cfg)
        assert fn is not None

    def test_top_n_passthrough(self):
        cfg = {"stock_selector": {"factors": ["calc_money_flow_6d"], "top_n": 100}}
        fn = build_stock_selector(cfg)
        assert fn is not None

    def test_min_pass_count_passthrough(self):
        cfg = {"stock_selector": {"factors": ["calc_money_flow_6d"], "min_pass_count": 3}}
        fn = build_stock_selector(cfg)
        assert fn is not None
