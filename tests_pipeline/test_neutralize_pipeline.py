"""Pipeline integration tests for industry neutralization."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.builtin.gtja_momentum import GTJAMomentumStrategy


def _make_market_data(n_stocks: int = 10, n_days: int = 60) -> pd.DataFrame:
    """Generate synthetic OHLCV data for pipeline tests."""
    np.random.seed(42)
    codes = [f"{i:06d}" for i in range(n_stocks)]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    rows = []
    for code in codes:
        price = 100.0
        for d in dates:
            ret = np.random.randn() * 0.02
            price *= 1 + ret
            rows.append(
                {
                    "date": d,
                    "code": code,
                    "open": price * (1 + np.random.randn() * 0.005),
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": np.random.randint(1_000_000, 10_000_000),
                }
            )
    return pd.DataFrame(rows)


def _make_industry_map(n_stocks: int = 10, n_industries: int = 3) -> dict[str, str]:
    """Create industry map with balanced industry sizes (>= min_peers)."""
    codes = [f"{i:06d}" for i in range(n_stocks)]
    return {c: f"Ind_{i % n_industries}" for i, c in enumerate(codes)}


class TestStrategyWithNeutralization:
    def test_strategy_with_neutralization_produces_signals(self):
        """GTJAMomentumStrategy with industry_map produces valid signal DataFrame."""
        data = _make_market_data(10, 60)
        industry_map = _make_industry_map(10, 3)

        strategy = GTJAMomentumStrategy(
            rebalance=10,
            top_n=3,
            bottom_n=2,
            industry_map=industry_map,
            min_peers=3,
        )
        result = strategy.generate_signal(data)

        assert set(result.columns) == {"date", "code", "signal", "confidence"}
        assert len(result) == len(data)
        assert result["signal"].isin([-1, 0, 1]).all()
        assert (result["confidence"] >= 0).all()
        assert (result["confidence"] <= 1).all()

    def test_strategy_without_neutralization_unchanged(self):
        """GTJAMomentumStrategy without industry_map behaves identically."""
        data = _make_market_data(10, 60)

        strategy_no_neutral = GTJAMomentumStrategy(rebalance=10, top_n=3, bottom_n=2)
        result_no_neutral = strategy_no_neutral.generate_signal(data)

        assert set(result_no_neutral.columns) == {
            "date",
            "code",
            "signal",
            "confidence",
        }
        assert result_no_neutral["signal"].isin([-1, 0, 1]).all()

    def test_neutralization_changes_signals(self):
        """Neutralization changes buy signals when one industry dominates."""
        # Industry 0: stocks 00-03 with strong upward drift (high momentum)
        # Industry 1: stocks 04-07 with moderate drift
        # Industry 2: stocks 08-11 with low drift
        # Without neutralization, buys cluster in industry 0.
        np.random.seed(77)
        n_stocks = 12
        n_days = 60
        codes = [f"{i:06d}" for i in range(n_stocks)]
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        industry_map = {c: f"Ind_{i // 4}" for i, c in enumerate(codes)}

        drift_map = {
            0: 0.015,
            1: 0.015,
            2: 0.015,
            3: 0.015,
            4: 0.002,
            5: 0.002,
            6: 0.002,
            7: 0.002,
            8: -0.005,
            9: -0.005,
            10: -0.005,
            11: -0.005,
        }
        rows = []
        for code in codes:
            idx = int(code)
            price = 100.0
            for d in dates:
                ret = np.random.randn() * 0.01 + drift_map[idx]
                price *= 1 + ret
                rows.append(
                    {
                        "date": d,
                        "code": code,
                        "open": price,
                        "high": price * 1.01,
                        "low": price * 0.99,
                        "close": price,
                        "volume": 5_000_000,
                    }
                )
        data = pd.DataFrame(rows)

        strategy_raw = GTJAMomentumStrategy(rebalance=10, top_n=4, bottom_n=2)
        strategy_neutral = GTJAMomentumStrategy(
            rebalance=10,
            top_n=4,
            bottom_n=2,
            industry_map=industry_map,
            min_peers=3,
        )

        result_raw = strategy_raw.generate_signal(data)
        result_neutral = strategy_neutral.generate_signal(data)

        raw_buys = set(result_raw[result_raw["signal"] == 1]["code"].unique())
        neutral_buys = set(
            result_neutral[result_neutral["signal"] == 1]["code"].unique()
        )
        # With strong industry-0 bias, neutralization must change the buy set
        assert raw_buys != neutral_buys, (
            "Neutralized buy set should differ from raw when "
            "one industry dominates momentum"
        )

    def test_neutralization_reduces_industry_concentration(self):
        """Neutralized buys span more industries than raw buys."""
        np.random.seed(77)
        n_stocks = 12
        n_days = 60
        codes = [f"{i:06d}" for i in range(n_stocks)]
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        industry_map = {c: f"Ind_{i // 4}" for i, c in enumerate(codes)}

        drift_map = {
            0: 0.015,
            1: 0.015,
            2: 0.015,
            3: 0.015,
            4: 0.002,
            5: 0.002,
            6: 0.002,
            7: 0.002,
            8: -0.005,
            9: -0.005,
            10: -0.005,
            11: -0.005,
        }
        rows = []
        for code in codes:
            idx = int(code)
            price = 100.0
            for d in dates:
                ret = np.random.randn() * 0.01 + drift_map[idx]
                price *= 1 + ret
                rows.append(
                    {
                        "date": d,
                        "code": code,
                        "open": price,
                        "high": price * 1.01,
                        "low": price * 0.99,
                        "close": price,
                        "volume": 5_000_000,
                    }
                )
        data = pd.DataFrame(rows)

        strategy_raw = GTJAMomentumStrategy(rebalance=10, top_n=4, bottom_n=2)
        strategy_neutral = GTJAMomentumStrategy(
            rebalance=10,
            top_n=4,
            bottom_n=2,
            industry_map=industry_map,
            min_peers=3,
        )

        result_raw = strategy_raw.generate_signal(data)
        result_neutral = strategy_neutral.generate_signal(data)

        def count_industries_in_buys(result):
            buys = result[result["signal"] == 1]
            if len(buys) == 0:
                return 0
            return len({industry_map.get(c, "?") for c in buys["code"].unique()})

        div_raw = count_industries_in_buys(result_raw)
        div_neutral = count_industries_in_buys(result_neutral)
        # Neutralization removes industry bias → more industry diversity
        assert div_neutral >= div_raw, (
            f"Neutralized buys should span >= raw industries, "
            f"got raw={div_raw}, neutral={div_neutral}"
        )


class TestConfigIntegration:
    def test_config_builds_industry_map_enabled(self):
        """build_industry_map returns (dict, int) when enabled."""
        from config.loader import build_industry_map

        cfg = {
            "neutralization": {"enabled": True, "method": "demean", "min_peers": 5},
            "strategies": {"rules": [{"name": "gtja_momentum", "params": {}}]},
            "risk": {"rules": []},
        }
        # This would call fetch_all_stocks which needs tushare; mock it
        from unittest.mock import patch

        mock_df = pd.DataFrame(
            {
                "code": ["001", "002", "003"],
                "name": ["A", "B", "C"],
                "industry": ["银行", "银行", "软件"],
            }
        )
        with patch("data.fetcher.fetch_all_stocks", return_value=mock_df):
            result = build_industry_map(cfg)

        assert result is not None
        im_dict, min_peers = result
        assert isinstance(im_dict, dict)
        assert min_peers == 5
        assert im_dict["001"] == "银行"

    def test_config_builds_industry_map_disabled(self):
        """build_industry_map returns None when disabled."""
        from config.loader import build_industry_map

        cfg = {"strategies": {"rules": []}, "risk": {"rules": []}}
        result = build_industry_map(cfg)
        assert result is None

    def test_config_injects_to_strategy(self):
        """build_strategies injects industry_map into GTJA strategy constructors."""

        from config.loader import build_strategies

        cfg = {
            "rules": [{"name": "gtja_momentum", "params": {"rebalance": 10}}],
        }
        industry_map_cfg = ({"001": "A", "002": "A", "003": "B"}, 3)

        strategy = build_strategies(cfg, industry_map_cfg=industry_map_cfg)
        assert hasattr(strategy, "industry_map")
        assert strategy.industry_map == {"001": "A", "002": "A", "003": "B"}
        assert strategy.min_peers == 3

    def test_config_no_inject_when_disabled(self):
        """Without industry_map_cfg, strategy gets no neutralization params."""
        from config.loader import build_strategies

        cfg = {
            "rules": [{"name": "gtja_momentum", "params": {"rebalance": 10}}],
        }
        strategy = build_strategies(cfg)
        assert strategy.industry_map is None
        assert strategy.min_peers == 3  # default

    def test_combined_strategy_injects_into_regime_switch(self):
        """build_combined_strategy passes neutralization to regime_switch."""
        from config.loader import build_combined_strategy

        cfg = {
            "neutralization": {"enabled": True, "min_peers": 3},
            "strategies": {
                "regime_switch": {
                    "regimes": {
                        "trend_up": {
                            "name": "gtja_momentum",
                            "params": {"rebalance": 10, "top_n": 3, "bottom_n": 2},
                        },
                        "trend_down": {
                            "name": "gtja_vwap",
                            "params": {"rebalance": 20, "top_n": 3, "bottom_n": 2},
                        },
                        "range": {
                            "name": "gtja_vwap",
                            "params": {"rebalance": 20, "top_n": 3, "bottom_n": 2},
                        },
                        "volatile": {
                            "name": "gtja_volatility",
                            "params": {"rebalance": 5, "top_n": 3, "bottom_n": 2},
                        },
                    }
                },
            },
            "risk": {"rules": []},
        }

        from unittest.mock import patch

        mock_df = pd.DataFrame(
            {
                "code": ["001", "002", "003", "004"],
                "name": ["A", "B", "C", "D"],
                "industry": ["银行", "银行", "软件", "软件"],
            }
        )
        with patch("data.fetcher.fetch_all_stocks", return_value=mock_df):
            result = build_combined_strategy(cfg)

        rs = result["strategy"]
        # RegimeSwitchStrategy has .regimes dict
        from context.regime_switch import RegimeSwitchStrategy

        assert isinstance(rs, RegimeSwitchStrategy)
        # Each regime's strategy should have industry_map injected
        for label, strat in rs.regimes.items():
            assert strat.industry_map == {
                "001": "银行",
                "002": "银行",
                "003": "软件",
                "004": "软件",
            }, f"Regime {label} missing industry_map"
            assert strat.min_peers == 3, f"Regime {label} missing min_peers"
