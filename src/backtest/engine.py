"""Lightweight backtest engine. No rqalpha dependency."""

from __future__ import annotations

import numpy as np
import pandas as pd


class BacktestEngine:
    """Simple event-driven backtest engine.

    Accepts pre-allocated positions (from portfolio + risk modules),
    executes buy/sell at close price, tracks cash + holdings,
    and computes equity curve + metrics.

    Data flow: signals -> portfolio -> risk -> BacktestEngine -> visualization
    """

    def __init__(self, capital: float = 1_000_000):
        self.initial_capital = capital
        self.cash = capital

    def run(
        self,
        positions: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> dict:
        """Run backtest on pre-allocated positions.

        Parameters
        ----------
        positions : DataFrame
            Target positions (date, code, weight, shares).
            Output of portfolio.allocator + risk.position_limit.
        prices : DataFrame
            Price data (date, code, close).

        Returns
        -------
        dict
            keys: trades (DataFrame), equity_curve (DataFrame), metrics (dict).
        """
        self.cash = self.initial_capital
        holdings: dict[str, int] = {}  # code -> shares held
        entry_prices: dict[str, float] = {}  # code -> buy price
        trades = []
        equity_rows = []

        all_dates = sorted(prices["date"].unique())
        price_map = prices.set_index(["date", "code"])["close"].to_dict()

        pos_cols = ["date", "code", "weight", "shares"]
        if positions.empty:
            positions = pd.DataFrame(columns=pos_cols)

        for date in all_dates:
            day_pos = positions[positions["date"] == date]
            day_prices = {
                code: price_map[(date, code)]
                for code in prices[prices["date"] == date]["code"]
                if (date, code) in price_map
            }

            target = {
                code: shares
                for code, shares in zip(day_pos["code"], day_pos["shares"])
                if shares > 0
            }

            # Sell positions not in target
            for code in list(holdings):
                if code not in target:
                    price = day_prices.get(code)
                    if price is None or (isinstance(price, float) and np.isnan(price)):
                        continue
                    shares = holdings.pop(code)
                    self.cash += shares * price
                    ep = entry_prices.pop(code, price)
                    pnl = shares * (price - ep)
                    trades.append({
                        "date": date, "code": code, "action": "sell",
                        "price": price, "shares": shares, "pnl": pnl,
                    })

            # Buy positions not in holdings
            for code, target_shares in target.items():
                if code not in holdings:
                    price = day_prices.get(code)
                    if price is None or (isinstance(price, float) and np.isnan(price)):
                        continue
                    shares = min(
                        int(self.cash / price / 100) * 100,
                        target_shares,
                    )
                    if shares > 0 and shares * price <= self.cash:
                        self.cash -= shares * price
                        holdings[code] = shares
                        entry_prices[code] = price
                        trades.append({
                            "date": date, "code": code, "action": "buy",
                            "price": price, "shares": shares, "pnl": 0.0,
                        })

            # End-of-day equity
            pos_value = sum(
                shares * day_prices.get(code, 0)
                for code, shares in holdings.items()
            )
            equity = self.cash + pos_value
            equity_rows.append({
                "date": date, "equity": equity, "cash": self.cash,
                "position_value": pos_value, "returns": 0.0,
            })

        cols_t = ["date", "code", "action", "price", "shares", "pnl"]
        cols_eq = ["date", "equity", "cash", "position_value", "returns"]
        trades_df = pd.DataFrame(trades, columns=cols_t)
        eq_df = pd.DataFrame(equity_rows, columns=cols_eq)

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

        n_days = len(eq)
        if n_days > 1 and total_return > -1:
            annual_return = (1 + total_return) ** (252 / n_days) - 1
        else:
            annual_return = 0.0

        daily_rf = 0.03 / 252
        returns = eq["returns"].values
        excess = returns - daily_rf
        sharpe = (
            (excess.mean() / excess.std() * np.sqrt(252))
            if excess.std() > 0
            else 0.0
        )

        equity = eq["equity"].values
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / np.where(peak > 0, peak, 1)
        max_drawdown = abs(drawdown.min())

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
