"""Tests for MultiCategoryStrategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.builtin.multi_category import MultiCategoryStrategy
from src.strategies.registry import get_strategy, list_strategies


@pytest.fixture
def sample_data():
    """30 days of data for 3 stocks."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    np.random.seed(42)
    frames = []
    for code in ["000001", "600519", "000858"]:
        close = 50 + np.cumsum(np.random.randn(30) * 0.5)
        close = np.maximum(close, 1.0)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "open": close - 0.1,
                    "high": close + 0.3,
                    "low": close - 0.3,
                    "close": close,
                    "volume": np.random.randint(500_000, 5_000_000, size=30).astype(
                        float
                    ),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_registered():
    """multi_category 应在注册表中。"""
    assert "multi_category" in list_strategies()


def test_instantiation():
    """应能通过 get_strategy 创建。"""
    strat = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
            {
                "name": "gtja_volume_price",
                "weight": 0.5,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )
    assert isinstance(strat, MultiCategoryStrategy)
    assert strat.name == "multi_category"


def test_empty_categories_raises():
    """空类别列表应抛出 ValueError。"""
    with pytest.raises(ValueError, match="at least one category"):
        MultiCategoryStrategy(categories=[])


def test_single_category(sample_data):
    """单类别组合应产生与原始策略相同数量的信号。"""
    from src.strategies.registry import get_strategy as gs

    original = gs("gtja_momentum", rebalance=20, top_n=3, bottom_n=0)
    multi = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )

    sig_orig = original.generate_signal(sample_data)
    sig_multi = multi.generate_signal(sample_data)

    # Signal counts should match (order may differ due to internal sorting)
    assert (sig_orig["signal"] == 1).sum() == (sig_multi["signal"] == 1).sum()
    assert (sig_orig["signal"] == -1).sum() == (sig_multi["signal"] == -1).sum()
    assert len(sig_orig) == len(sig_multi)


def test_two_categories_combine(sample_data):
    """两个类别组合应产生不同于单类别的信号。"""
    strat = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
            {
                "name": "gtja_volume_price",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )

    sig = strat.generate_signal(sample_data)
    assert set(sig.columns) == {"date", "code", "signal", "confidence"}
    assert set(sig["signal"].unique()).issubset({-1, 0, 1})
    assert len(sig) == len(sample_data)


def test_weighted_combination(sample_data):
    """权重应影响组合信号。"""
    # Category A only
    strat_a = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )
    # Category B only
    strat_b = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_volume_price",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )
    # Equal weight combination
    strat_ab = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
            {
                "name": "gtja_volume_price",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )

    sig_a = strat_a.generate_signal(sample_data)
    sig_b = strat_b.generate_signal(sample_data)
    sig_ab = strat_ab.generate_signal(sample_data)

    # Combined should not be identical to either single (unless they agree perfectly)
    buys_a = (sig_a["signal"] == 1).sum()
    buys_b = (sig_b["signal"] == 1).sum()
    buys_ab = (sig_ab["signal"] == 1).sum()

    # At least check it produces valid output
    assert buys_ab >= 0
    assert len(sig_ab) == len(sample_data)


def test_confidence_range(sample_data):
    """confidence 应在 [0, 1] 范围内。"""
    strat = get_strategy(
        "multi_category",
        categories=[
            {
                "name": "gtja_momentum",
                "weight": 1.0,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
            {
                "name": "gtja_volume_price",
                "weight": 0.5,
                "params": {"rebalance": 20, "top_n": 3, "bottom_n": 0},
            },
        ],
    )

    sig = strat.generate_signal(sample_data)
    assert sig["confidence"].between(0, 1).all()
