"""Config loader tests."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.config.loader import build_risk_engine, build_strategies, load_config
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
