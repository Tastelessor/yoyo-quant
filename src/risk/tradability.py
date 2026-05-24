"""A 股可交易性风控规则。

基于行情数据中的市场状态标注（limit_up / limit_down / is_suspended）
过滤不可执行的交易信号，并执行 T+1 规则。
"""

from __future__ import annotations

import pandas as pd

from src.risk.rules import Rule, RuleContext


class TradabilityRule(Rule):
    """Rule wrapper for filter_tradable.

    Reads limit_up / limit_down / is_suspended from market_data,
    filters untradeable signals in-place.
    """

    name = "tradability"
    priority = 200

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.signals = filter_tradable(ctx.market_data, ctx.signals)
        return ctx


class T1Rule(Rule):
    """Rule wrapper for enforce_t1 (T+1 constraint)."""

    name = "t1"
    priority = 210

    def apply(self, ctx: RuleContext) -> RuleContext:
        ctx.signals = enforce_t1(ctx.signals)
        return ctx


def filter_tradable(
    market: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    """过滤不可交易的信号。

    规则：
    - 涨停日不生成买入信号
    - 跌停日不生成卖出信号
    - 停牌日不生成任何信号

    Parameters
    ----------
    market : DataFrame
        行情数据，必须包含 date, code, limit_up, limit_down, is_suspended 列。
        这些列由 data.filters.detect_limit_price / detect_suspension 标注。
    signals : DataFrame
        信号数据（date, code, signal, confidence）。

    Returns
    -------
    DataFrame
        过滤后的信号，不可交易的 signal 置为 0。
    """
    merged = signals.merge(
        market[["date", "code", "limit_up", "limit_down", "is_suspended"]],
        on=["date", "code"],
        how="left",
    )

    # 涨停日买入 → 过滤
    buy_blocked = (merged["signal"] == 1) & (merged["limit_up"] | merged["is_suspended"])
    # 跌停日卖出 → 过滤
    sell_blocked = (merged["signal"] == -1) & (merged["limit_down"] | merged["is_suspended"])

    merged.loc[buy_blocked | sell_blocked, "signal"] = 0
    merged.loc[buy_blocked | sell_blocked, "confidence"] = 0.0

    return merged[["date", "code", "signal", "confidence"]]


def enforce_t1(signals: pd.DataFrame) -> pd.DataFrame:
    """执行 T+1 规则：买入当日不可卖出。

    如果某日买入（signal=1），则同日的卖出信号无效。
    实际场景中，持仓状态需要跨日维护，这里只处理同日冲突。

    Parameters
    ----------
    signals : DataFrame
        信号数据。

    Returns
    -------
    DataFrame
        处理后的信号。
    """
    signals = signals.sort_values(["code", "date"]).reset_index(drop=True)

    # 同一日内如果既有买入又有卖出（不应发生），以买入优先
    # 在实际回测中，T+1 由持仓状态控制，这里做防御性处理
    dup = signals.duplicated(subset=["date", "code"], keep=False)
    if dup.any():
        # 同日多条信号：保留 signal=1（买入），其余置 0
        mask = dup & (signals["signal"] != 1)
        signals.loc[mask, "signal"] = 0
        signals.loc[mask, "confidence"] = 0.0

    return signals
