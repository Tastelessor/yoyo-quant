"""Lightweight backtest engine. No rqalpha dependency."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TradingCost:
    """A-share trading friction parameters.

    Attributes
    ----------
    commission : float
        Commission rate (e.g. 0.0001 for 0.01%). Applied to both buy and sell.
        Minimum 5 CNY per trade.
    stamp_tax : float
        Stamp tax rate (e.g. 0.0005 for 0.05%). Sell-side only.
    transfer_fee : float
        Transfer fee rate (e.g. 0.00001 for 0.001%). Both sides.
    slippage_ticks : int
        Number of price ticks to slip (each tick = 0.01 CNY).
    """

    commission: float = 0.0001
    stamp_tax: float = 0.0005
    transfer_fee: float = 0.00001
    slippage_ticks: int = 1

    def __post_init__(self):
        for name in ("commission", "stamp_tax", "transfer_fee"):
            if getattr(self, name) < 0:
                raise ValueError(
                    f"{name} must be >= 0, got {getattr(self, name)}"
                )
        if self.slippage_ticks < 0:
            raise ValueError(
                f"slippage_ticks must be >= 0, got {self.slippage_ticks}"
            )


class BacktestEngine:
    """Simple event-driven backtest engine.

    Accepts pre-allocated positions (from portfolio + risk modules),
    executes buy/sell at close price, tracks cash + holdings,
    and computes equity curve + metrics.

    Parameters
    ----------
    capital : float
        Initial cash.
    stop_loss : float | None
        Stop-loss threshold (e.g. -0.15 for -15%). None to disable.
    take_profit : float | None
        Take-profit threshold (e.g. 0.05 for +5%). None to disable.
    atr_stop_loss : dict | None
        ATR-based dynamic stop-loss config with keys
        ``atr_multiplier`` (float, default 3.0) and ``atr_window``
        (int, default 14).  None to disable.
    trading_cost : TradingCost | None
        Trading friction parameters. None disables all friction.

    Data flow: signals -> portfolio -> risk -> BacktestEngine -> visualization
    """

    def __init__(
        self,
        capital: float = 1_000_000,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        atr_stop_loss: dict | None = None,
        trading_cost: TradingCost | None = None,
        circuit_breaker: object | None = None,
    ):
        self.initial_capital = capital
        self.cash = capital
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.atr_stop_loss = atr_stop_loss
        self.trading_cost = trading_cost
        self.circuit_breaker = circuit_breaker

    def _apply_slippage(
        self, price: float, is_sell: bool,
        limit_up: float | None = None, limit_down: float | None = None,
    ) -> float:
        """Adjust execution price by slippage ticks, clipped to limit prices.

        Note: limit_up/limit_down are expected to be float prices or None.
        Boolean values (from market data flags) are ignored.
        """
        if self.trading_cost is None or self.trading_cost.slippage_ticks == 0:
            return price
        delta = self.trading_cost.slippage_ticks * 0.01
        exec_price = price - delta if is_sell else price + delta
        if not is_sell and isinstance(limit_up, (int, float)) and not isinstance(limit_up, bool):
            exec_price = min(exec_price, limit_up)
        if is_sell and isinstance(limit_down, (int, float)) and not isinstance(limit_down, bool):
            exec_price = max(exec_price, limit_down)
        return exec_price

    def _calc_cost(self, amount: float, is_sell: bool) -> float:
        """Calculate total friction cost for a single trade."""
        if self.trading_cost is None or amount <= 0:
            return 0.0
        tc = self.trading_cost
        cost = 0.0
        if tc.commission > 0:
            cost += max(amount * tc.commission, 5.0)
        if is_sell and tc.stamp_tax > 0:
            cost += amount * tc.stamp_tax
        if tc.transfer_fee > 0:
            cost += amount * tc.transfer_fee
        return cost

    def run(
        self,
        positions: pd.DataFrame,
        prices: pd.DataFrame,
        market_data: pd.DataFrame | None = None,
        starting_capital: float | None = None,
    ) -> dict:
        """Run backtest on pre-allocated positions.

        Parameters
        ----------
        positions : DataFrame
            Target positions (date, code, weight, shares).
            Output of portfolio.allocator + risk.position_limit.
        prices : DataFrame
            Price data (date, code, close).
        market_data : DataFrame | None
            Full OHLCV data (date, code, open, high, low, close, volume).
            Required when ``atr_stop_loss`` is enabled.
        starting_capital : float | None
            Override initial capital for this run. When chaining walk-forward
            periods, pass the previous period's ending equity here.
            Defaults to self.initial_capital.

        Returns
        -------
        dict
            keys: trades (DataFrame), equity_curve (DataFrame), metrics (dict).
        """
        init = starting_capital if starting_capital is not None else self.initial_capital
        self.cash = init
        holdings: dict[str, int] = {}  # code -> shares held
        entry_prices: dict[str, float] = {}  # code -> buy price
        trades = []
        equity_rows = []
        _prev_equity: float = init  # for circuit breaker
        _equity_history: list[float] = [init]  # for momentum
        _active_exposure: float = 1.0  # current applied exposure
        if self.circuit_breaker is not None:
            self.circuit_breaker.reset()

        all_dates = sorted(prices["date"].unique())
        price_map = prices.set_index(["date", "code"])["close"].to_dict()

        # Pre-compute ATR for all (date, code) pairs
        atr_map: dict[tuple, float] = {}
        if self.atr_stop_loss is not None:
            if market_data is None:
                raise ValueError(
                    "atr_stop_loss requires market_data (OHLCV) to be passed to run()"
                )
            from factors.volume_price import calc_atr

            window = self.atr_stop_loss.get("atr_window", 14)
            # calc_atr sorts internally by ["code", "date"], so we must
            # align our key construction to that same order.
            sorted_md = market_data.sort_values(
                ["code", "date"]
            ).reset_index(drop=True)
            atr_series = calc_atr(sorted_md, window=window)
            atr_map = dict(zip(
                zip(sorted_md["date"], sorted_md["code"]),
                atr_series.values,
            ))

        pos_cols = ["date", "code", "weight", "shares"]
        if positions.empty:
            positions = pd.DataFrame(columns=pos_cols)

        # Pre-group by date to avoid O(N) full-table scans inside daily loop
        pos_by_date = {
            d: g for d, g in positions.groupby("date")
        }
        codes_by_date = {
            d: g["code"].tolist()
            for d, g in prices.groupby("date")
        }
        md_by_date: dict = {}
        if market_data is not None:
            if ("limit_up" in market_data.columns
                    and "limit_down" in market_data.columns):
                for d, g in market_data.groupby("date"):
                    md_by_date[d] = g.set_index("code")[
                        ["limit_up", "limit_down"]
                    ].to_dict(orient="index")
            else:
                md_by_date = {}

        for date in all_dates:
            stopped_today: set[str] = set()

            day_pos = pos_by_date.get(date, pd.DataFrame(columns=pos_cols))
            day_prices = {
                code: price_map[(date, code)]
                for code in codes_by_date.get(date, [])
                if (date, code) in price_map
            }

            # Daily limit price lookup (O(1) per code)
            day_limits = md_by_date.get(date, {})

            target = {
                code: shares
                for code, shares in zip(day_pos["code"], day_pos["shares"])
                if shares > 0
            }

            # Circuit breaker: scale target based on yesterday's drawdown
            if self.circuit_breaker is not None and _prev_equity > 0:
                cb = self.circuit_breaker
                peak = max(_prev_equity, cb._peak)
                cb._peak = peak
                dd = (_prev_equity - peak) / peak
                new_exposure = cb._drawdown_to_exposure(dd)

                # Fast recovery: momentum quench bypasses hysteresis
                if cb.check_fast_recovery(_equity_history):
                    new_exposure = 1.0

                # Dead-zone: only adjust if change is significant
                if abs(new_exposure - _active_exposure) > cb.dead_zone:
                    _active_exposure = new_exposure

                if _active_exposure < 1.0:
                    target = {
                        code: int(shares * _active_exposure)
                        for code, shares in target.items()
                    }

            # Stop-loss / take-profit on existing holdings
            for code in list(holdings):
                price = day_prices.get(code)
                if price is None or (isinstance(price, float) and np.isnan(price)):
                    continue
                ep = entry_prices.get(code, price)
                pnl_pct = (price - ep) / ep if ep > 0 else 0.0

                triggered = False
                reason = ""

                # ATR-based stop-loss (check first, takes priority)
                if self.atr_stop_loss is not None:
                    atr = atr_map.get((date, code))
                    if atr is not None and not np.isnan(atr) and ep > 0:
                        multiplier = self.atr_stop_loss.get("atr_multiplier", 3.0)
                        stop_price = ep - multiplier * atr
                        if price < stop_price:
                            triggered = True
                            reason = "atr_stop_loss"

                # Fixed stop-loss (independent of ATR config)
                if not triggered and self.stop_loss is not None:
                    if pnl_pct < self.stop_loss:
                        triggered = True
                        reason = "stop_loss"

                # Fixed take-profit (only if neither stop triggered)
                if not triggered and self.take_profit is not None:
                    if pnl_pct > self.take_profit:
                        triggered = True
                        reason = "take_profit"

                if triggered:
                    shares = holdings.pop(code)
                    limits = day_limits.get(code, {})
                    exec_price = self._apply_slippage(
                        price, is_sell=True,
                        limit_up=limits.get("limit_up"),
                        limit_down=limits.get("limit_down"),
                    )
                    sell_amount = shares * exec_price
                    sell_fees = self._calc_cost(sell_amount, is_sell=True)
                    self.cash += sell_amount - sell_fees
                    entry_prices.pop(code, None)
                    stopped_today.add(code)
                    pnl = shares * (exec_price - ep) - sell_fees
                    trades.append({
                        "date": date, "code": code, "action": reason,
                        "price": exec_price, "shares": shares,
                        "pnl": pnl, "cost": sell_fees,
                    })

            # Sell positions not in target or over target (CB compression)
            for code in list(holdings):
                target_shares = target.get(code, 0)
                held_shares = holdings[code]
                excess = held_shares - target_shares
                if excess <= 0:
                    continue
                price = day_prices.get(code)
                if price is None or (isinstance(price, float) and np.isnan(price)):
                    continue
                limits = day_limits.get(code, {})
                exec_price = self._apply_slippage(
                    price, is_sell=True,
                    limit_up=limits.get("limit_up"),
                    limit_down=limits.get("limit_down"),
                )
                sell_amount = excess * exec_price
                sell_fees = self._calc_cost(sell_amount, is_sell=True)
                self.cash += sell_amount - sell_fees
                ep = entry_prices.get(code, price)
                pnl = excess * (exec_price - ep) - sell_fees
                action = "sell" if target_shares == 0 else "cb_compress"
                trades.append({
                    "date": date, "code": code, "action": action,
                    "price": exec_price, "shares": excess,
                    "pnl": pnl, "cost": sell_fees,
                })
                if target_shares == 0:
                    holdings.pop(code)
                    entry_prices.pop(code, None)
                else:
                    holdings[code] = target_shares

            # Buy positions not in holdings (skip stocks stopped today)
            for code, target_shares in target.items():
                if code not in holdings and code not in stopped_today:
                    price = day_prices.get(code)
                    if price is None or (isinstance(price, float) and np.isnan(price)):
                        continue
                    limits = day_limits.get(code, {})
                    exec_price = self._apply_slippage(
                        price, is_sell=False,
                        limit_up=limits.get("limit_up"),
                        limit_down=limits.get("limit_down"),
                    )

                    # Precise inverse calculation for max affordable shares
                    tc = self.trading_cost
                    if tc is not None and exec_price > 0:
                        # Case A: min commission applies → V*(1+transfer)+5<=cash
                        v_max_min = (self.cash - 5.0) / (1.0 + tc.transfer_fee)
                        # Case B: proportional commission → V*(1+comm+transfer)<=cash
                        v_max_prop = self.cash / (
                            1.0 + tc.commission + tc.transfer_fee
                        )
                        v_max = min(v_max_min, v_max_prop)
                    else:
                        v_max = self.cash

                    if v_max <= 0 or exec_price <= 0:
                        shares = 0
                    else:
                        shares = min(
                            int(v_max / exec_price / 100) * 100,
                            target_shares,
                        )

                    if shares > 0:
                        buy_amount = shares * exec_price
                        buy_fees = self._calc_cost(buy_amount, is_sell=False)
                        total_buy_cost = buy_amount + buy_fees
                        # Float tolerance 0.01 CNY to prevent false rejection
                        if total_buy_cost <= self.cash + 0.01:
                            self.cash -= total_buy_cost
                            # All-in cost price: buy fees amortized into avg cost
                            entry_prices[code] = (
                                (buy_amount + buy_fees) / shares
                            )
                            holdings[code] = shares
                            trades.append({
                                "date": date, "code": code, "action": "buy",
                                "price": exec_price, "shares": shares,
                                "pnl": 0.0, "cost": buy_fees,
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
            _prev_equity = equity
            _equity_history.append(equity)

        cols_t = ["date", "code", "action", "price", "shares", "pnl", "cost"]
        cols_eq = ["date", "equity", "cash", "position_value", "returns"]
        trades_df = pd.DataFrame(trades, columns=cols_t)
        eq_df = pd.DataFrame(equity_rows, columns=cols_eq)

        if len(eq_df) > 1:
            eq_df["returns"] = eq_df["equity"].pct_change().fillna(0.0)

        metrics = self._calc_metrics(eq_df, trades_df, initial=init)

        return {"trades": trades_df, "equity_curve": eq_df, "metrics": metrics}

    def _calc_metrics(
        self, eq: pd.DataFrame, trades: pd.DataFrame, initial: float | None = None,
    ) -> dict:
        """Calculate performance metrics."""
        if initial is None:
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

        exit_actions = ["sell", "stop_loss", "take_profit", "atr_stop_loss"]
        sell_trades = trades[trades["action"].isin(exit_actions)]
        if len(sell_trades) > 0:
            win_rate = (sell_trades["pnl"] > 0).mean()
        else:
            win_rate = 0.0

        # Trading cost metrics
        total_cost = trades["cost"].sum() if len(trades) > 0 else 0.0
        turnover = (
            (trades["shares"] * trades["price"]).sum()
            if len(trades) > 0 else 0.0
        )
        cost_ratio = total_cost / turnover if turnover > 0 else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "trade_count": len(trades),
            "total_cost": total_cost,
            "cost_ratio": cost_ratio,
        }
