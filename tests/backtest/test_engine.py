"""Lightweight backtest engine tests."""

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine


@pytest.fixture
def prices():
    """5 days of prices for 2 stocks."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    )
    return pd.DataFrame(
        {
            "date": dates.tolist() * 2,
            "code": ["000001"] * 5 + ["600519"] * 5,
            "close": [
                10.0, 10.5, 11.0, 10.8, 11.2,
                1800.0, 1810.0, 1790.0, 1820.0, 1850.0,
            ],
        }
    )


@pytest.fixture
def buy_positions():
    """Buy 000001 on day 1, hold through all days."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04",
         "2024-01-05", "2024-01-08"]
    )
    return pd.DataFrame(
        {
            "date": dates,
            "code": ["000001"] * 5,
            "weight": [1.0] * 5,
            "shares": [10000] * 5,
        }
    )


@pytest.fixture
def buy_sell_positions():
    """Buy on day 1, hold through day 3, sell on day 4."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04",
         "2024-01-05", "2024-01-08"]
    )
    return pd.DataFrame(
        {
            "date": dates,
            "code": ["000001"] * 5,
            "weight": [1.0, 1.0, 1.0, 0.0, 0.0],
            "shares": [10000, 10000, 10000, 0, 0],
        }
    )


def test_engine_init():
    engine = BacktestEngine(capital=100_000)
    assert engine.initial_capital == 100_000
    assert engine.cash == 100_000


def test_run_returns_dict(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    assert isinstance(result, dict)
    assert "trades" in result
    assert "equity_curve" in result
    assert "metrics" in result


def test_trades_has_required_columns(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    trades = result["trades"]
    expected = {"date", "code", "action", "price", "shares", "pnl"}
    assert set(trades.columns) == expected


def test_equity_curve_has_required_columns(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    eq = result["equity_curve"]
    expected = {"date", "equity", "cash", "position_value", "returns"}
    assert set(eq.columns) == expected


def test_metrics_has_required_keys(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    metrics = result["metrics"]
    expected = {
        "total_return", "annual_return", "sharpe_ratio",
        "max_drawdown", "win_rate", "trade_count",
    }
    assert set(metrics.keys()) == expected


def test_buy_generates_trade(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    trades = result["trades"]
    buys = trades[trades["action"] == "buy"]
    assert len(buys) == 1
    assert buys.iloc[0]["code"] == "000001"


def test_sell_generates_trade(prices, buy_sell_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_positions, prices)
    trades = result["trades"]
    assert len(trades) == 2  # 1 buy + 1 sell
    assert set(trades["action"]) == {"buy", "sell"}


def test_equity_starts_at_capital(prices):
    """No positions → equity equals capital on all days."""
    engine = BacktestEngine(capital=100_000)
    empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
    result = engine.run(empty, prices)
    eq = result["equity_curve"]
    assert (eq["equity"] == 100_000).all()


def test_equity_changes_after_buy(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    eq = result["equity_curve"]
    # After buying, cash drops, equity tracks price changes
    assert eq.iloc[1]["cash"] < 100_000
    assert eq.iloc[1]["position_value"] > 0


def test_no_positions_no_trades(prices):
    engine = BacktestEngine(capital=100_000)
    empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
    result = engine.run(empty, prices)
    assert len(result["trades"]) == 0
    eq = result["equity_curve"]
    assert (eq["equity"] == 100_000).all()


def test_total_return_zero_when_no_trades(prices):
    engine = BacktestEngine(capital=100_000)
    empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
    result = engine.run(empty, prices)
    assert result["metrics"]["total_return"] == 0.0


def test_total_return_positive_on_profit(prices, buy_sell_positions):
    """Buy at 10.0, sell at 10.8 → profit."""
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_positions, prices)
    assert result["metrics"]["total_return"] > 0


def test_trade_count(prices, buy_sell_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_positions, prices)
    assert result["metrics"]["trade_count"] == 2


def test_shares_round_to_100(prices, buy_positions):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_positions, prices)
    for _, row in result["trades"].iterrows():
        assert row["shares"] % 100 == 0


def test_nan_price_skipped(prices):
    """NaN price should not crash; position is skipped."""
    positions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "code": ["000001"],
            "weight": [1.0],
            "shares": [10000],
        }
    )
    # Inject NaN price
    prices_nan = prices.copy()
    prices_nan.loc[
        (prices_nan["date"] == pd.Timestamp("2024-01-02"))
        & (prices_nan["code"] == "000001"),
        "close",
    ] = np.nan
    engine = BacktestEngine(capital=100_000)
    result = engine.run(positions, prices_nan)
    # No trade generated due to NaN price
    assert len(result["trades"]) == 0
    assert (result["equity_curve"]["equity"] == 100_000).all()


# ---------------------------------------------------------------------------
# ATR stop-loss tests
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlcv_data():
    """Full OHLCV market data for ATR computation.

    000001: rises from 10.0 to 11.5 then drops sharply to 9.0
            (ATR ~0.5, stop at entry - 0.1*ATR = 9.95, triggers when < 9.95)
    600519: stable around 1800
    """
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15",
    ])
    return pd.DataFrame({
        "date": dates.tolist() * 2,
        "code": ["000001"] * 10 + ["600519"] * 10,
        "open": [
            10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.0, 10.0, 9.0,
            1800.0, 1810.0, 1790.0, 1820.0, 1850.0, 1840.0, 1830.0, 1810.0,
            1800.0, 1790.0,
        ],
        "high": [
            10.2, 10.7, 11.2, 11.0, 11.5, 11.7, 11.5, 11.2, 10.2, 9.2,
            1810.0, 1820.0, 1800.0, 1830.0, 1860.0, 1850.0, 1840.0, 1820.0,
            1810.0, 1800.0,
        ],
        "low": [
            9.8, 10.3, 10.8, 10.6, 11.0, 11.3, 11.1, 10.8, 9.8, 8.8,
            1790.0, 1800.0, 1780.0, 1810.0, 1840.0, 1830.0, 1820.0, 1800.0,
            1790.0, 1780.0,
        ],
        "close": [
            10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.0, 10.0, 9.0,
            1800.0, 1810.0, 1790.0, 1820.0, 1850.0, 1840.0, 1830.0, 1810.0,
            1800.0, 1790.0,
        ],
        "volume": [1_000_000] * 20,
    })


@pytest.fixture
def ohlcv_prices():
    """Price subset from ohlcv_data (date, code, close)."""
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15",
    ])
    return pd.DataFrame({
        "date": dates.tolist() * 2,
        "code": ["000001"] * 10 + ["600519"] * 10,
        "close": [
            10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 11.3, 11.0, 10.0, 9.0,
            1800.0, 1810.0, 1790.0, 1820.0, 1850.0, 1840.0, 1830.0, 1810.0,
            1800.0, 1790.0,
        ],
    })


class TestATRStopLoss:
    def test_atr_stop_requires_market_data(self):
        """atr_stop_loss without market_data raises ValueError."""
        engine = BacktestEngine(
            capital=100_000,
            atr_stop_loss={"atr_multiplier": 3.0, "atr_window": 5},
        )
        positions = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        prices = pd.DataFrame(columns=["date", "code", "close"])
        with pytest.raises(ValueError, match="atr_stop_loss requires market_data"):
            engine.run(positions, prices)

    def test_atr_stop_loss_triggers_on_drop(self, ohlcv_data, ohlcv_prices):
        """Stock dropping below ATR stop triggers sell."""
        all_dates = ohlcv_prices["date"].unique()
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        atr_trades = result["trades"][
            result["trades"]["action"] == "atr_stop_loss"
        ]
        assert len(atr_trades) >= 1

    def test_atr_stop_no_trigger_when_stable(self, ohlcv_data, ohlcv_prices):
        """Wide multiplier prevents ATR stop from triggering."""
        all_dates = ohlcv_prices["date"].unique()
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 10.0, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        atr_trades = result["trades"][
            result["trades"]["action"] == "atr_stop_loss"
        ]
        assert len(atr_trades) == 0

    def test_atr_stop_generates_correct_trade_action(self, ohlcv_data, ohlcv_prices):
        """ATR stop trade has action='atr_stop_loss'."""
        all_dates = ohlcv_prices["date"].unique()
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        actions = set(result["trades"]["action"].unique())
        assert "atr_stop_loss" in actions

    def test_combined_atr_and_fixed_stop(self, ohlcv_data, ohlcv_prices):
        """Both ATR and fixed stop configured; ATR triggers first."""
        all_dates = ohlcv_prices["date"].unique()
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            stop_loss=-0.50,  # very wide fixed stop, won't trigger
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        atr_trades = result["trades"][
            result["trades"]["action"] == "atr_stop_loss"
        ]
        fixed_trades = result["trades"][
            result["trades"]["action"] == "stop_loss"
        ]
        assert len(atr_trades) >= 1
        assert len(fixed_trades) == 0  # ATR took priority

    def test_stopped_today_prevents_rebuy(self, ohlcv_data, ohlcv_prices):
        """Stock stopped out today is NOT re-bought the same day."""
        all_dates = ohlcv_prices["date"].unique()
        # Target always includes 000001 (would normally re-buy after stop)
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        trades = result["trades"]
        atr_trades = trades[trades["action"] == "atr_stop_loss"]
        if len(atr_trades) > 0:
            stop_date = atr_trades.iloc[0]["date"]
            stop_code = atr_trades.iloc[0]["code"]
            # No buy on the same date for the same code
            same_day_buy = trades[
                (trades["date"] == stop_date)
                & (trades["code"] == stop_code)
                & (trades["action"] == "buy")
            ]
            assert len(same_day_buy) == 0

    def test_entry_prices_cleaned_on_stop(self, ohlcv_data, ohlcv_prices):
        """After ATR stop, re-buy PnL is based on new entry price.

        If entry_prices wasn't cleaned, the engine would use the old entry
        price for PnL calculation on the re-buy, which is wrong.
        We verify by checking that the re-buy trade's PnL is 0.0 (fresh entry).
        """
        all_dates = ohlcv_prices["date"].unique()
        positions = pd.DataFrame({
            "date": all_dates,
            "code": ["000001"] * len(all_dates),
            "weight": [1.0] * len(all_dates),
            "shares": [10000] * len(all_dates),
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, ohlcv_prices, market_data=ohlcv_data)
        trades = result["trades"]
        atr_trades = trades[trades["action"] == "atr_stop_loss"]
        buy_trades = trades[trades["action"] == "buy"]
        if len(atr_trades) > 0 and len(buy_trades) > 0:
            # Re-buy after stop should have PnL=0 (fresh entry, not old cost)
            stop_date = atr_trades.iloc[0]["date"]
            re_buys = buy_trades[buy_trades["date"] > stop_date]
            if len(re_buys) > 0:
                assert (re_buys["pnl"] == 0.0).all()

    def test_atr_map_with_date_interleaved_data(self):
        """ATR map must be correct when market_data is date-sorted (not code-sorted).

        calc_atr sorts internally by ["code", "date"], so the engine must
        align the returned values to (date, code) keys correctly.
        """
        dates = pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
            "2024-01-08", "2024-01-09", "2024-01-10",
        ])
        # Date-interleaved: each date has both stocks
        ohlcv = pd.DataFrame({
            "date": dates.tolist() * 2,
            "code": ["000001"] * 7 + ["600519"] * 7,
            "open": [10, 11, 12, 11, 10, 9, 8,
                     100, 101, 99, 98, 97, 96, 95],
            "high": [10.2, 11.2, 12.2, 11.2, 10.2, 9.2, 8.2,
                     101, 102, 100, 99, 98, 97, 96],
            "low": [9.8, 10.8, 11.8, 10.8, 9.8, 8.8, 7.8,
                    99, 100, 98, 97, 96, 95, 94],
            "close": [10, 11, 12, 11, 10, 9, 8,
                      100, 101, 99, 98, 97, 96, 95],
            "volume": [1_000_000] * 14,
        })
        prices = ohlcv[["date", "code", "close"]].copy()
        # Only hold 000001, which drops from 10 to 8
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 7,
            "weight": [1.0] * 7,
            "shares": [10000] * 7,
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 3},
        )
        result = engine.run(positions, prices, market_data=ohlcv)
        # ATR stop should trigger for 000001 (dropping from 10 to 8)
        atr_trades = result["trades"][
            result["trades"]["action"] == "atr_stop_loss"
        ]
        assert len(atr_trades) >= 1
        assert atr_trades.iloc[0]["code"] == "000001"

    def test_nan_atr_skips_gracefully(self):
        """Stock with insufficient history → ATR is NaN → no crash."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 9.5],
        })
        ohlcv = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "open": [10.0, 9.5],
            "high": [10.2, 9.7],
            "low": [9.8, 9.3],
            "close": [10.0, 9.5],
            "volume": [1_000_000] * 2,
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0] * 2,
            "shares": [10000] * 2,
        })
        engine = BacktestEngine(
            capital=100_000,
            atr_stop_loss={"atr_multiplier": 3.0, "atr_window": 14},
        )
        # Should not crash despite insufficient data for ATR
        result = engine.run(positions, prices, market_data=ohlcv)
        assert result["metrics"]["trade_count"] >= 0

    def test_stopped_today_cleared_each_day(self):
        """stopped_today resets per day — stock can be re-bought next day.

        Uses 2-day scenario: stop on day 1, re-buy on day 2.
        """
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        # Day 1: price drops to trigger stop. Day 2-3: target still present.
        ohlcv = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 3,
            "open": [10.0, 8.0, 8.5],
            "high": [10.2, 8.2, 8.7],
            "low": [9.8, 7.8, 8.3],
            "close": [10.0, 8.0, 8.5],
            "volume": [1_000_000] * 3,
        })
        prices = ohlcv[["date", "code", "close"]].copy()
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 3,
            "weight": [1.0] * 3,
            "shares": [10000] * 3,
        })
        engine = BacktestEngine(
            capital=1_000_000,
            atr_stop_loss={"atr_multiplier": 0.1, "atr_window": 2},
        )
        result = engine.run(positions, prices, market_data=ohlcv)
        trades = result["trades"]
        atr_trades = trades[trades["action"] == "atr_stop_loss"]
        if len(atr_trades) > 0:
            stop_date = atr_trades.iloc[0]["date"]
            # Same-day re-buy must be blocked
            same_day_buys = trades[
                (trades["date"] == stop_date) & (trades["action"] == "buy")
            ]
            assert len(same_day_buys) == 0
            # Later re-buy must be allowed (stopped_today cleared)
            later_buys = trades[
                (trades["date"] > stop_date) & (trades["action"] == "buy")
            ]
            assert len(later_buys) >= 1
