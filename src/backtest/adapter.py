"""将 yoyo-quant 策略管道适配为 rqalpha 回测。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import pandas as pd

from src.strategies.builtin.mean_reversion import mean_reversion_signal

if TYPE_CHECKING:
    pass


def build_strategy_config(
    code: str,
    start_date: str,
    end_date: str,
    frequency: str = "1d",
    account_type: str = "stock",
    initial_cash: float = 1_000_000,
) -> dict[str, Any]:
    """构建 rqalpha 回测配置。

    Parameters
    ----------
    code : str
        股票代码，如 "000001"。
    start_date, end_date : str
        回测日期范围 "YYYY-MM-DD"。
    frequency : str
        回测频率，默认 "1d"。
    account_type : str
        账户类型，默认 "stock"。
    initial_cash : float
        初始资金。

    Returns
    -------
    dict
        rqalpha config 字典。
    """
    symbol = f"{code}.XSHG" if code.startswith("6") else f"{code}.XSHE"
    return {
        "base": {
            "start_date": start_date,
            "end_date": end_date,
            "frequency": frequency,
            "accounts": {account_type: initial_cash},
            "benchmark": None,
        },
        "extra": {
            "log_level": "error",
        },
        "mod": {
            "sys_analyser": {
                "enabled": True,
                "report_save_path": None,
            },
        },
    }


def make_init(
    code: str,
    window: int = 20,
    num_std: float = 2.0,
) -> Callable:
    """生成 rqalpha init 函数。

    Parameters
    ----------
    code : str
        股票代码。
    window : int
        均值回归窗口。
    num_std : float
        标准差倍数。

    Returns
    -------
    callable
        init(context) 函数。
    """
    symbol = f"{code}.XSHG" if code.startswith("6") else f"{code}.XSHE"

    def init(context):
        context.symbol = symbol
        context.window = window
        context.num_std = num_std
        context.positioned = False
        context.subscribe(context.symbol)

    return init


def make_handle_bar(
    window: int = 20,
    num_std: float = 2.0,
) -> Callable:
    """生成 rqalpha handle_bar 函数。

    使用均值回归信号驱动交易。

    Parameters
    ----------
    window : int
        均值回归窗口。
    num_std : float
        标准差倍数。

    Returns
    -------
    callable
        handle_bar(context, bar_dict) 函数。
    """

    def handle_bar(context, bar_dict):
        symbol = context.symbol
        bar = bar_dict[symbol]

        # 获取历史数据
        prices = context.history_bars(context.window + 1, "1d", "close")

        if prices is None or len(prices) < context.window:
            return

        # 构造 DataFrame 计算信号
        df = pd.DataFrame(
            {
                "date": pd.Timestamp.now(),
                "code": symbol,
                "close": prices,
            }
        )
        signals = mean_reversion_signal(df, window=context.window, num_std=context.num_std)
        signal = signals["signal"].iloc[-1]

        position = context.portfolio.positions[symbol]

        if signal == 1 and not context.positioned:
            # 买入：全仓
            context.order_target_percent(symbol, 1.0)
            context.positioned = True
        elif signal == -1 and context.positioned:
            # 卖出：清仓
            context.order_target_percent(symbol, 0.0)
            context.positioned = False

    return handle_bar
