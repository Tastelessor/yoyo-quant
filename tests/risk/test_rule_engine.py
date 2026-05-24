"""Rule engine and Rule ABC tests."""

import numpy as np
import pandas as pd
import pytest

from src.risk.rules import Rule, RuleContext
from src.risk.rule_engine import RuleEngine


# --- Fixtures ---


@pytest.fixture
def sample_ctx():
    """Minimal RuleContext with signals, positions, market_data."""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "code": ["000001", "600519"],
            "signal": [1, -1],
            "confidence": [0.8, 0.6],
        }
    )
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 2),
            "code": ["000001", "600519"],
            "weight": [0.5, 0.5],
            "shares": [5000, 100],
        }
    )
    market = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 2),
            "code": ["000001", "600519"],
            "close": [10.0, 500.0],
        }
    )
    return RuleContext(signals=signals, positions=positions, market_data=market)


# --- Concrete rule for testing ---


class ZeroConfidenceRule(Rule):
    """Test rule: sets all confidence to 0."""

    name = "zero_confidence"
    priority = 100

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.signals["confidence"] = 0.0
        return ctx


class DoubleWeightRule(Rule):
    """Test rule: doubles all position weights."""

    name = "double_weight"
    priority = 150

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.positions["weight"] = ctx.positions["weight"] * 2
        return ctx


class MetadataRule(Rule):
    """Test rule: writes a marker into metadata."""

    name = "metadata_marker"
    priority = 50

    def __init__(self, key: str, value: str):
        self._key = key
        self._value = value

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.metadata[self._key] = self._value
        return ctx


# --- RuleContext tests ---


class TestRuleContext:
    def test_default_metadata_is_empty_dict(self, sample_ctx):
        assert sample_ctx.metadata == {}

    def test_metadata_shared_across_rules(self, sample_ctx):
        """Rules writing to ctx.metadata should see each other's changes."""
        engine = RuleEngine(
            rules=[
                MetadataRule("step", "first"),
                MetadataRule("status", "done"),
            ]
        )
        result = engine.run(sample_ctx)
        assert result.metadata == {"step": "first", "status": "done"}

    def test_signals_positions_mutable(self, sample_ctx):
        """Rules should be able to modify signals and positions in-place."""
        engine = RuleEngine(rules=[ZeroConfidenceRule()])
        result = engine.run(sample_ctx)
        assert (result.signals["confidence"] == 0.0).all()


# --- RuleEngine tests ---


class TestRuleEngine:
    def test_empty_rules_returns_ctx_unchanged(self, sample_ctx):
        engine = RuleEngine(rules=[])
        result = engine.run(sample_ctx)
        pd.testing.assert_frame_equal(result.signals, sample_ctx.signals)
        pd.testing.assert_frame_equal(result.positions, sample_ctx.positions)

    def test_single_rule_applied(self, sample_ctx):
        engine = RuleEngine(rules=[ZeroConfidenceRule()])
        result = engine.run(sample_ctx)
        assert (result.signals["confidence"] == 0.0).all()

    def test_rules_sorted_by_priority(self, sample_ctx):
        """Lower priority number runs first."""
        rule_a = MetadataRule("order", "a")  # priority=50
        rule_b = MetadataRule("order", "b")  # priority=50, same

        # Same priority → registration order preserved
        engine = RuleEngine(rules=[rule_a, rule_b])
        result = engine.run(sample_ctx)
        # rule_a overwrites, then rule_b overwrites
        assert result.metadata["order"] == "b"

    def test_priority_ordering_enforced(self, sample_ctx):
        """Rule with priority 50 runs before priority 150."""
        log = []

        class LoggingRule(Rule):
            def __init__(self, name: str, priority: int):
                self._name = name
                self._priority = priority

            @property
            def name(self):
                return self._name

            @property
            def priority(self):
                return self._priority

            def apply(self, ctx):
                log.append(self._name)
                return ctx

        engine = RuleEngine(
            rules=[
                LoggingRule("late", 150),
                LoggingRule("early", 50),
                LoggingRule("mid", 100),
            ]
        )
        engine.run(sample_ctx)
        assert log == ["early", "mid", "late"]

    def test_chained_rules_share_ctx(self, sample_ctx):
        """Rule A modifies ctx, Rule B sees the modification."""
        engine = RuleEngine(
            rules=[ZeroConfidenceRule(), DoubleWeightRule()]
        )
        result = engine.run(sample_ctx)
        # ZeroConfidence ran first (priority=100), DoubleWeight second (priority=150)
        assert (result.signals["confidence"] == 0.0).all()
        np.testing.assert_allclose(
            result.positions["weight"].values, [1.0, 1.0]
        )

    def test_rule_exception_propagates(self, sample_ctx):
        class BadRule(Rule):
            name = "bad"
            priority = 100

            def apply(self, ctx):
                raise ValueError("rule failed")

        engine = RuleEngine(rules=[BadRule()])
        with pytest.raises(ValueError, match="rule failed"):
            engine.run(sample_ctx)

    def test_rules_property_returns_sorted_list(self, sample_ctx):
        engine = RuleEngine(
            rules=[
                ZeroConfidenceRule(),  # 100
                MetadataRule("x", "y"),  # 50
            ]
        )
        names = [r.name for r in engine.rules]
        assert names == ["metadata_marker", "zero_confidence"]


# --- Rule ABC contract tests ---


class TestRuleABC:
    def test_cannot_instantiate_abstract_rule(self):
        with pytest.raises(TypeError):
            Rule()

    def test_concrete_rule_satisfies_interface(self):
        rule = ZeroConfidenceRule()
        assert rule.name == "zero_confidence"
        assert rule.priority == 100
        ctx = RuleContext(
            signals=pd.DataFrame(),
            positions=pd.DataFrame(),
            market_data=pd.DataFrame(),
        )
        result = rule.apply(ctx)
        assert isinstance(result, RuleContext)

    def test_rule_missing_name_raises(self):
        class NoNameRule(Rule):
            priority = 100

            def apply(self, ctx):
                return ctx

        with pytest.raises(TypeError):
            NoNameRule()

    def test_rule_missing_priority_raises(self):
        class NoPriorityRule(Rule):
            name = "test"

            def apply(self, ctx):
                return ctx

        with pytest.raises(TypeError):
            NoPriorityRule()

    def test_rule_missing_apply_raises(self):
        class NoApplyRule(Rule):
            name = "test"
            priority = 100

        with pytest.raises(TypeError):
            NoApplyRule()
