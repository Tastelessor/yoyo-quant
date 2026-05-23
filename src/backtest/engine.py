"""Lightweight backtest engine. No rqalpha dependency."""

from __future__ import annotations

import numpy as np
import pandas as pd


class BacktestEngine:
    """Simple event-driven backtest engine.

    Iterates over dates, executes buy/sell signals at close price,
    tracks cash + positions, and computes equity curve + metrics.
    """

    def __init__(self, capital: float = 1_000_000):
        self.initial_capital = capital
        self.cash = capital

    def run(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> dict:
        """Run backtest.

        Parameters
        ----------
        signals : DataFrame
            Signal data (date, code, signal, confidence).
        prices : DataFrame
            OHLCV or price data (date, code, close).

        Returns
        -------
        dict
            keys: trades (DataFrame), equity_curve (DataFrame), metrics (dict).
        """
        self.cash = self.initial_capital
        positions: dict[str, int] = {}  # code -> shares held
        trades = []
        equity_rows = []

        all_dates = sorted(prices["date"].unique())
        price_map = prices.set_index(["date", "code"])["close"].to_dict()

        for date in all_dates:
            if signals.empty:
                day_signals = pd.DataFrame()
            else:
                day_signals = signals[signals["date"] == date]
            day_prices = {
                code: price_map[(date, code)]
                for code in prices[prices["date"] == date]["code"]
                if (date, code) in price_map
            }

            # Execute signals
            for _, sig in day_signals.iterrows():
                code = sig["code"]
                price = day_prices.get(code)
                if price is None:
                    continue

                if sig["signal"] == 1 and code not in positions:
                    # Buy: allocate equal portion of available cash
                    buy_codes = day_signals[day_signals["signal"] == 1]["code"].tolist()
                    alloc = self.cash / len(buy_codes) if buy_codes else 0
                    shares = int(alloc / price / 100) * 100
                    if shares > 0 and shares * price <= self.cash:
                        self.cash -= shares * price
                        positions[code] = shares
                        trades.append(
                            {
                                "date": date,
                                "code": code,
                                "action": "buy",
                                "price": price,
                                "shares": shares,
                                "pnl": 0.0,
                            }
                        )

                elif sig["signal"] == -1 and code in positions:
                    # Sell
                    shares = positions.pop(code)
                    proceeds = shares * price
                    self.cash += proceeds
                    # PnL vs entry (approximate: use first buy price if available)
                    entry_price = next(
                        (t["price"] for t in trades
                         if t["code"] == code and t["action"] == "buy"),
                        price,
                    )
                    pnl = shares * (price - entry_price)
                    trades.append(
                        {
                            "date": date,
                            "code": code,
                            "action": "sell",
                            "price": price,
                            "shares": shares,
                            "pnl": pnl,
                        }
                    )

            # Calculate end-of-day equity
            pos_value = sum(
                shares * day_prices.get(code, 0) for code, shares in positions.items()
            )
            equity = self.cash + pos_value
            equity_rows.append(
                {
                    "date": date,
                    "equity": equity,
                    "cash": self.cash,
                    "position_value": pos_value,
                    "returns": 0.0,  # filled below
                }
            )

        cols_t = ["date", "code", "action", "price", "shares", "pnl"]
        cols_eq = ["date", "equity", "cash", "position_value", "returns"]
        trades_df = pd.DataFrame(trades, columns=cols_t)
        eq_df = pd.DataFrame(equity_rows, columns=cols_eq)

        # Calculate daily returns
        if len(eq_df) > 1:
            eq_df["returns"] = eq_df["equity"].pct_change().fillna(0.0)

        metrics = self._calc_metrics(eq_df, trades_df)

        return {"trades": trades_df, "equity_curve": eq_df, "metrics": metrics}

    def _calc_metrics(
        self, eq: pd.DataFrame, trades: pd.DataFrame
    ) -> dict:
        """Calculate performance metrics."""
        initial = self.initial_capital
        final = eq.iloc[-1]["equity"] if len(eq) > 0 else initial

        total_return = (final - initial) / initial if initial > 0 else 0.0

        # Annualized return (252 trading days)
        n_days = len(eq)
        if n_days > 1 and total_return > -1:
            annual_return = (1 + total_return) ** (252 / n_days) - 1
        else:
            annual_return = 0.0

        # Sharpe ratio (risk-free rate = 3%)
        daily_rf = 0.03 / 252
        returns = eq["returns"].values
        excess = returns - daily_rf
        sharpe = (
            (excess.mean() / excess.std() * np.sqrt(252))
            if excess.std() > 0
            else 0.0
        )

        # Max drawdown
        equity = eq["equity"].values
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / np.where(peak > 0, peak, 1)
        max_drawdown = abs(drawdown.min())

        # Win rate
        sell_trades = trades[trades["action"] == "sell"]
        if len(sell_trades) > 0:
            win_rate = (sell_trades["pnl"] > 0).mean()
        else:
            win_rate = 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "trade_count": len(trades),
        }
