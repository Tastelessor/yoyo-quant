"""Position limit risk rule tests."""

import numpy as np
import pandas as pd
import pytest

from risk.position_limit import PositionLimitRule, apply_position_limit
from risk.rules import RuleContext


@pytest.fixture
def positions():
    """3 stocks, equal weight."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 3),
            "code": ["000001", "600519", "000858"],
            "weight": [1 / 3, 1 / 3, 1 / 3],
            "shares": [3300, 100, 600],
        }
    )


@pytest.fixture
def concentrated_positions():
    """One stock dominates."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 3),
            "code": ["000001", "600519", "000858"],
            "weight": [0.7, 0.2, 0.1],
            "shares": [7000, 100, 200],
        }
    )


def test_returns_dataframe(positions):
    result = apply_position_limit(positions, max_weight=0.5)
    assert isinstance(result, pd.DataFrame)


def test_has_required_columns(positions):
    result = apply_position_limit(positions, max_weight=0.5)
    assert set(result.columns) == {"date", "code", "weight", "shares"}


def test_no_change_when_within_limit(positions):
    """All weights below max_weight → no change."""
    result = apply_position_limit(positions, max_weight=0.5)
    np.testing.assert_allclose(result["weight"].values, 1 / 3, atol=1e-8)


def test_cap_concentrated_position(concentrated_positions):
    """0.7 weight capped to 0.5, excess redistributed."""
    result = apply_position_limit(concentrated_positions, max_weight=0.5)
    weights = result.sort_values("code")["weight"].values
    assert weights.max() <= 0.5 + 1e-8
    # Total weight must still sum to 1
    np.testing.assert_allclose(weights.sum(), 1.0, atol=1e-8)


def test_cap_preserves_order(concentrated_positions):
    """Same stocks in output."""
    result = apply_position_limit(concentrated_positions, max_weight=0.5)
    assert set(result["code"]) == {"000001", "600519", "000858"}


def test_all_positions_exceed_cap():
    """When all exceed max_weight, all capped at max, sum < 1."""
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 2),
            "code": ["000001", "600519"],
            "weight": [0.6, 0.4],
            "shares": [6000, 200],
        }
    )
    result = apply_position_limit(positions, max_weight=0.3)
    weights = result.sort_values("code")["weight"].values
    # Both capped at 0.3, excess dropped (becomes cash)
    assert weights[0] <= 0.3 + 1e-8
    assert weights[1] <= 0.3 + 1e-8
    # Sum < 1 because excess is dropped
    assert weights.sum() < 1.0


def test_single_stock_exceeds_cap():
    """Single stock at 1.0, capped to max_weight."""
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "code": ["000001"],
            "weight": [1.0],
            "shares": [10000],
        }
    )
    result = apply_position_limit(positions, max_weight=0.3)
    assert result.iloc[0]["weight"] <= 0.3 + 1e-8


def test_zero_max_weight():
    """max_weight=0 → all weights become 0."""
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 2),
            "code": ["000001", "600519"],
            "weight": [0.6, 0.4],
            "shares": [6000, 200],
        }
    )
    result = apply_position_limit(positions, max_weight=0.0)
    assert (result["weight"] == 0).all()


def test_empty_positions():
    empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
    result = apply_position_limit(empty, max_weight=0.3)
    assert len(result) == 0


def test_multi_day_positions():
    """Each day processed independently."""
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "code": ["000001", "600519", "000001", "600519"],
            "weight": [0.8, 0.2, 0.3, 0.7],
            "shares": [8000, 100, 3000, 350],
        }
    )
    result = apply_position_limit(positions, max_weight=0.5)
    for date in result["date"].unique():
        day = result[result["date"] == date]
        assert day["weight"].max() <= 0.5 + 1e-8
        np.testing.assert_allclose(day["weight"].sum(), 1.0, atol=1e-8)


# --- PositionLimitRule (Rule ABC wrapper) ---


@pytest.fixture
def rule_ctx(positions):
    """RuleContext wrapping the positions fixture."""
    return RuleContext(
        signals=pd.DataFrame(),
        positions=positions,
        market_data=pd.DataFrame(),
    )


def test_rule_name_and_priority():
    rule = PositionLimitRule(max_weight=0.5)
    assert rule.name == "position_limit"
    assert rule.priority == 150


def test_rule_caps_position(rule_ctx):
    rule = PositionLimitRule(max_weight=0.5)
    result = rule.apply(rule_ctx)
    assert result.positions["weight"].max() <= 0.5 + 1e-8


def test_rule_returns_rule_context(rule_ctx):
    rule = PositionLimitRule(max_weight=0.5)
    result = rule.apply(rule_ctx)
    assert isinstance(result, RuleContext)


def test_rule_preserves_signals_and_market_data(rule_ctx):
    rule = PositionLimitRule(max_weight=0.5)
    result = rule.apply(rule_ctx)
    pd.testing.assert_frame_equal(result.signals, rule_ctx.signals)
    pd.testing.assert_frame_equal(result.market_data, rule_ctx.market_data)
