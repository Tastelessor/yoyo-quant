"""Strategy registry tests."""

import pandas as pd
import pytest

from strategies.base import Strategy
from strategies.registry import get_strategy, list_strategies, register_strategy


class TestRegistry:
    def test_register_and_get(self):
        @register_strategy("reg_test_buy")
        class TestStrat(Strategy):
            name = "reg_test_buy"

            def generate_signal(self, data, factors=None):
                return pd.DataFrame()

        strat = get_strategy("reg_test_buy")
        assert isinstance(strat, Strategy)
        assert strat.name == "reg_test_buy"

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError, match="nonexistent_reg"):
            get_strategy("nonexistent_reg")

    def test_list_strategies(self):
        names = list_strategies()
        assert isinstance(names, list)
        assert "reg_test_buy" in names

    def test_register_with_params(self):
        @register_strategy("reg_test_parametric")
        class ParametricStrat(Strategy):
            name = "reg_test_parametric"

            def __init__(self, window: int = 20):
                self.window = window

            def generate_signal(self, data, factors=None):
                return pd.DataFrame()

        strat = get_strategy("reg_test_parametric", window=50)
        assert strat.window == 50
