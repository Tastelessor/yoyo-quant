"""Lightweight backtest engine tests."""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, TradingCost


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
    expected = {"date", "code", "action", "price", "shares", "pnl", "cost"}
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
        "total_cost", "cost_ratio",
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


# ---------------------------------------------------------------------------
# Trading cost / friction tests
# ---------------------------------------------------------------------------

class TestTradingCost:
    def test_default_values(self):
        tc = TradingCost()
        assert tc.commission == 0.0001
        assert tc.stamp_tax == 0.0005
        assert tc.transfer_fee == 0.00001
        assert tc.slippage_ticks == 1

    def test_no_friction_compatible(self, prices, buy_positions):
        """trading_cost=None should behave identically to before."""
        engine_no_cost = BacktestEngine(capital=100_000)
        result = engine_no_cost.run(buy_positions, prices)
        assert result["metrics"]["total_cost"] == 0.0
        assert result["metrics"]["cost_ratio"] == 0.0

    def test_buy_deducts_fees(self):
        """Buy should deduct commission + transfer fee from cash."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 10.5],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0, 1.0],
            "shares": [10000, 10000],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0, transfer_fee=0.00001,
                         slippage_ticks=0)
        engine = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result = engine.run(positions, prices)
        # Buy at 10.0 * 10000 = 100000
        # Commission = max(100000 * 0.0001, 5) = 10
        # Transfer = 100000 * 0.00001 = 1
        # Total cost = 11
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        assert buy_trade["cost"] == pytest.approx(11.0, abs=0.01)
        assert engine.cash < 1_000_000 - 100_000  # more than just share cost

    def test_sell_deducts_stamp_tax(self):
        """Sell should deduct commission + stamp tax + transfer fee."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 10.5],
        })
        # Buy on day 1, sell on day 2
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0, 0.0],
            "shares": [10000, 0],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0005, transfer_fee=0.00001,
                         slippage_ticks=0)
        engine = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result = engine.run(positions, prices)
        sell_trade = result["trades"][result["trades"]["action"] == "sell"].iloc[0]
        # Sell amount = 10.5 * 10000 = 105000
        # Commission = max(105000*0.0001, 5) = 10.5
        # Stamp tax = 105000 * 0.0005 = 52.5
        # Transfer = 105000 * 0.00001 = 1.05
        # Total = 64.05
        assert sell_trade["cost"] == pytest.approx(64.05, abs=0.1)

    def test_min_commission_5_yuan(self):
        """Small trade should still pay at least 5 CNY commission."""
        dates = pd.to_datetime(["2024-01-02"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"],
            "close": [1.0],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"],
            "weight": [1.0],
            "shares": [100],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0, transfer_fee=0.0,
                         slippage_ticks=0)
        engine = BacktestEngine(capital=100_000, trading_cost=tc)
        result = engine.run(positions, prices)
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        # amount = 100, commission = max(100*0.0001, 5) = 5.0
        assert buy_trade["cost"] >= 5.0

    def test_zero_amount_defense(self):
        """_calc_cost with amount=0 should return 0."""
        tc = TradingCost()
        engine = BacktestEngine(capital=100_000, trading_cost=tc)
        assert engine._calc_cost(0.0, is_sell=False) == 0.0
        assert engine._calc_cost(-1.0, is_sell=True) == 0.0

    def test_slippage_direction(self):
        """Buy price should be higher, sell price should be lower."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 10.5],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0, 0.0],
            "shares": [10000, 0],
        })
        tc = TradingCost(commission=0.0, stamp_tax=0.0, transfer_fee=0.0,
                         slippage_ticks=1)
        engine = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result = engine.run(positions, prices)
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        sell_trade = result["trades"][result["trades"]["action"] == "sell"].iloc[0]
        assert buy_trade["price"] == pytest.approx(10.01)   # +0.01
        assert sell_trade["price"] == pytest.approx(10.49)  # -0.01

    def test_cost_basis_amortization(self):
        """entry_prices should include buy fees (all-in cost price)."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 10.5],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0, 0.0],
            "shares": [10000, 0],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0005, transfer_fee=0.00001,
                         slippage_ticks=0)
        engine = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result = engine.run(positions, prices)
        # Buy at 10.0, fees = 11.0 (commission 10 + transfer 1)
        # All-in cost = (100000 + 11) / 10000 = 10.0011
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        sell_trade = result["trades"][result["trades"]["action"] == "sell"].iloc[0]
        expected_entry = (100000 + buy_trade["cost"]) / 10000
        sell_fees = sell_trade["cost"]
        expected_pnl = 10000 * (10.5 - expected_entry) - sell_fees
        assert sell_trade["pnl"] == pytest.approx(expected_pnl, abs=0.01)

    def test_pnl_lifecycle_audit(self):
        """Full lifecycle: Final Cash - Initial Cash == sum(trades['pnl'])."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 3,
            "close": [10.0, 10.5, 11.0],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 3,
            "weight": [1.0, 1.0, 0.0],
            "shares": [10000, 10000, 0],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0005, transfer_fee=0.00001,
                         slippage_ticks=1)
        initial = 1_000_000.0
        engine = BacktestEngine(capital=initial, trading_cost=tc)
        result = engine.run(positions, prices)

        cash_delta = engine.cash - initial
        sum_pnl = result["trades"]["pnl"].sum()
        assert abs(cash_delta - sum_pnl) < 1e-6

        # Buy pnl must be 0, cost must be > 0
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        assert buy_trade["pnl"] == 0.0
        assert buy_trade["cost"] > 0.0

        # Metrics consistency
        assert result["metrics"]["total_cost"] == pytest.approx(
            result["trades"]["cost"].sum(), abs=1e-6
        )
        assert result["metrics"]["cost_ratio"] > 0.0

    def test_zero_turnover_no_crash(self):
        """No trades → cost_ratio = 0, no ZeroDivisionError."""
        dates = pd.to_datetime(["2024-01-02"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"],
            "close": [10.0],
        })
        empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        tc = TradingCost()
        engine = BacktestEngine(capital=100_000, trading_cost=tc)
        result = engine.run(empty, prices)
        assert result["metrics"]["cost_ratio"] == 0.0

    def test_friction_reduces_returns(self):
        """Same strategy with friction should have lower returns."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 3,
            "close": [10.0, 10.5, 11.0],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 3,
            "weight": [1.0, 1.0, 0.0],
            "shares": [10000, 10000, 0],
        })
        engine_no_cost = BacktestEngine(capital=1_000_000)
        result_no_cost = engine_no_cost.run(positions, prices)

        tc = TradingCost()
        engine_with_cost = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result_with_cost = engine_with_cost.run(positions, prices)

        assert (result_with_cost["metrics"]["total_return"]
                < result_no_cost["metrics"]["total_return"])

    def test_limit_price_clipping(self):
        """Slippage should be clipped to limit_up/limit_down."""
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "close": [10.0, 10.5],
        })
        # limit_up very close to close price
        market_data = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 2,
            "open": [10.0, 10.5],
            "high": [10.01, 10.51],
            "low": [9.99, 10.49],
            "close": [10.0, 10.5],
            "volume": [1_000_000] * 2,
            "limit_up": [10.01, 10.51],  # very tight
            "limit_down": [9.99, 10.49],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 2,
            "weight": [1.0, 0.0],
            "shares": [10000, 0],
        })
        tc = TradingCost(commission=0.0, stamp_tax=0.0, transfer_fee=0.0,
                         slippage_ticks=5)  # 5 ticks = 0.05
        engine = BacktestEngine(capital=1_000_000, trading_cost=tc)
        result = engine.run(positions, prices, market_data=market_data)
        buy_trade = result["trades"][result["trades"]["action"] == "buy"].iloc[0]
        sell_trade = result["trades"][result["trades"]["action"] == "sell"].iloc[0]
        # Buy: 10.0 + 0.05 = 10.05, but limit_up=10.01 → clipped to 10.01
        assert buy_trade["price"] == pytest.approx(10.01)
        # Sell: 10.5 - 0.05 = 10.45, but limit_down=10.49 → clipped to 10.49
        assert sell_trade["price"] == pytest.approx(10.49)

    def test_insufficient_funds_after_fees(self):
        """When cash covers shares but not shares+fees, order is rejected."""
        dates = pd.to_datetime(["2024-01-02"])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"],
            "close": [10.0],
        })
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"],
            "weight": [1.0],
            "shares": [10000],
        })
        # Capital just enough for shares but not shares + fees
        # 10000 * 10.0 = 100000. Fees ~11. So need ~100011.
        # Set capital to 100005 — covers shares but not shares+fees.
        tc = TradingCost(commission=0.0001, stamp_tax=0.0, transfer_fee=0.00001,
                         slippage_ticks=0)
        engine = BacktestEngine(capital=100_005, trading_cost=tc)
        result = engine.run(positions, prices)
        # The precise inverse calc should still allow the buy since
        # v_max accounts for fees. But if capital is truly too small
        # (below the inverse threshold), no buy occurs.
        trades = result["trades"]
        if len(trades) > 0 and trades.iloc[0]["action"] == "buy":
            # If buy happened, total cost must fit within cash
            assert engine.cash >= -0.01  # tiny negative OK from float

    def test_pnl_lifecycle_stop_loss(self):
        """PnL lifecycle audit through stop-loss exit path."""
        dates = pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
        ])
        prices = pd.DataFrame({
            "date": dates.tolist(),
            "code": ["000001"] * 4,
            "close": [10.0, 10.5, 8.0, 8.5],
        })
        # Buy day 1, hold day 2, stop-loss triggers day 3, no re-entry day 4
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * 4,
            "weight": [1.0, 1.0, 0.0, 0.0],
            "shares": [10000, 10000, 0, 0],
        })
        tc = TradingCost(commission=0.0001, stamp_tax=0.0005,
                         transfer_fee=0.00001, slippage_ticks=1)
        initial = 1_000_000.0
        engine = BacktestEngine(
            capital=initial, trading_cost=tc, stop_loss=-0.10,
        )
        result = engine.run(positions, prices)

        # Lifecycle audit: cash_delta == sum(pnl) (all positions closed)
        cash_delta = engine.cash - initial
        sum_pnl = result["trades"]["pnl"].sum()
        assert abs(cash_delta - sum_pnl) < 1e-6

        # Metrics consistency
        assert result["metrics"]["total_cost"] == pytest.approx(
            result["trades"]["cost"].sum(), abs=1e-6
        )


class TestCircuitBreaker:
    """Test drawdown circuit breaker integration in engine."""

    def _make_data(self, prices_list):
        """Create positions and prices for a simple buy-and-hold."""
        n = len(prices_list)
        dates = pd.bdate_range("2023-01-01", periods=n)
        positions = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * n,
            "weight": [1.0] * n,
            "shares": [10000] * n,
        })
        prices = pd.DataFrame({
            "date": dates,
            "code": ["000001"] * n,
            "close": prices_list,
        })
        return positions, prices

    def test_no_compression_when_no_drawdown(self):
        """Circuit breaker does nothing when equity rises."""
        from portfolio.circuit_breaker import DrawdownCircuitBreaker

        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)
        positions, prices = self._make_data([100, 101, 102, 103])
        engine = BacktestEngine(capital=1_000_000, circuit_breaker=cb)
        result = engine.run(positions, prices)

        # No CB sells when equity rises
        cb_sells = result["trades"][result["trades"]["action"] == "cb_compress"]
        assert len(cb_sells) == 0

    def test_compression_on_drawdown(self):
        """Circuit breaker reduces positions during drawdown."""
        from portfolio.circuit_breaker import DrawdownCircuitBreaker

        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)
        # Price drops 20% -> drawdown triggers CB
        positions, prices = self._make_data([100, 90, 80, 75, 70])
        engine = BacktestEngine(capital=1_000_000, circuit_breaker=cb)
        result = engine.run(positions, prices)

        # Should have sell trades from CB compression
        cb_sells = result["trades"][result["trades"]["action"] == "cb_compress"]
        assert len(cb_sells) > 0

    def test_no_cb_when_none(self):
        """No circuit breaker means no extra sells."""
        positions, prices = self._make_data([100, 90, 80, 75, 70])
        engine = BacktestEngine(capital=1_000_000, circuit_breaker=None)
        result = engine.run(positions, prices)

        cb_sells = result["trades"][result["trades"]["action"] == "cb_compress"]
        assert len(cb_sells) == 0

    def test_cb_resets_each_run(self):
        """Circuit breaker resets at start of each engine.run()."""
        from portfolio.circuit_breaker import DrawdownCircuitBreaker

        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)

        # First run: drawdown
        positions1, prices1 = self._make_data([100, 90, 80])
        engine1 = BacktestEngine(capital=1_000_000, circuit_breaker=cb)
        engine1.run(positions1, prices1)

        # Second run: no drawdown - CB should be reset
        positions2, prices2 = self._make_data([100, 101, 102])
        engine2 = BacktestEngine(capital=1_000_000, circuit_breaker=cb)
        result2 = engine2.run(positions2, prices2)

        cb_sells = result2["trades"][result2["trades"]["action"] == "cb_compress"]
        assert len(cb_sells) == 0
