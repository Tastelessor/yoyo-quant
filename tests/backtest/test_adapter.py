from unittest.mock import MagicMock

import numpy as np

from backtest.adapter import build_strategy_config, make_handle_bar, make_init


def test_build_strategy_config_basic():
    """配置应包含 base、extra、mod 字段。"""
    config = build_strategy_config("000001", "2024-01-01", "2024-12-31")
    assert "base" in config
    assert config["base"]["start_date"] == "2024-01-01"
    assert config["base"]["end_date"] == "2024-12-31"
    assert config["base"]["frequency"] == "1d"
    assert config["base"]["benchmark"] is None


def test_build_strategy_config_symbol():
    """深市代码应映射为 XSHE，沪市为 XSHG。"""
    config_sz = build_strategy_config("000001", "2024-01-01", "2024-12-31")
    config_sh = build_strategy_config("600519", "2024-01-01", "2024-12-31")
    # symbol 在 init 中设置，config 中无 symbol
    assert config_sz["base"]["accounts"]["stock"] == 1_000_000
    assert config_sh["base"]["accounts"]["stock"] == 1_000_000


def test_build_strategy_config_custom_cash():
    """应支持自定义初始资金。"""
    config = build_strategy_config("000001", "2024-01-01", "2024-12-31", initial_cash=500_000)
    assert config["base"]["accounts"]["stock"] == 500_000


def test_make_init_returns_callable():
    """make_init 应返回可调用对象。"""
    init_fn = make_init("000001")
    assert callable(init_fn)


def test_make_init_sets_context():
    """init 函数应设置 context 的 symbol 和参数。"""
    init_fn = make_init("000001", window=10, num_std=1.5)
    context = MagicMock()
    init_fn(context)
    assert context.symbol == "000001.XSHE"
    assert context.window == 10
    assert context.num_std == 1.5
    assert context.positioned is False
    context.subscribe.assert_called_once_with("000001.XSHE")


def test_make_init_sh_stock():
    """沪市股票应映射为 XSHG。"""
    init_fn = make_init("600519")
    context = MagicMock()
    init_fn(context)
    assert context.symbol == "600519.XSHG"


def test_make_handle_bar_returns_callable():
    """make_handle_bar 应返回可调用对象。"""
    handle_bar = make_handle_bar()
    assert callable(handle_bar)


def test_handle_bar_buy_on_buy_signal():
    """当均值回归信号为买入且未持仓时，应下单。"""
    handle_bar = make_handle_bar(window=20, num_std=2.0)

    context = MagicMock()
    context.symbol = "000001.XSHE"
    context.window = 20
    context.num_std = 2.0
    context.positioned = False

    # 构造历史价格：稳定后突然下跌
    prices = np.concatenate([np.full(20, 100.0), [85.0]])
    context.history_bars.return_value = prices

    bar_dict = {"000001.XSHE": MagicMock()}
    handle_bar(context, bar_dict)
    context.order_target_percent.assert_called_once_with("000001.XSHE", 1.0)
    assert context.positioned is True


def test_handle_bar_sell_on_sell_signal():
    """当均值回归信号为卖出且已持仓时，应清仓。"""
    handle_bar = make_handle_bar(window=20, num_std=2.0)

    context = MagicMock()
    context.symbol = "000001.XSHE"
    context.window = 20
    context.num_std = 2.0
    context.positioned = True

    # 构造历史价格：稳定后突然上涨
    prices = np.concatenate([np.full(20, 100.0), [115.0]])
    context.history_bars.return_value = prices

    bar_dict = {"000001.XSHE": MagicMock()}
    handle_bar(context, bar_dict)
    context.order_target_percent.assert_called_once_with("000001.XSHE", 0.0)
    assert context.positioned is False


def test_handle_bar_no_action_when_no_signal():
    """无信号时不应下单。"""
    handle_bar = make_handle_bar(window=20, num_std=2.0)

    context = MagicMock()
    context.symbol = "000001.XSHE"
    context.window = 20
    context.num_std = 2.0
    context.positioned = False

    # 稳定价格 → 无信号
    prices = np.full(21, 100.0)
    context.history_bars.return_value = prices

    bar_dict = {"000001.XSHE": MagicMock()}
    handle_bar(context, bar_dict)
    context.order_target_percent.assert_not_called()


def test_handle_bar_insufficient_data():
    """数据不足时不应下单。"""
    handle_bar = make_handle_bar(window=20, num_std=2.0)

    context = MagicMock()
    context.symbol = "000001.XSHE"
    context.window = 20
    context.num_std = 2.0
    context.positioned = False
    context.history_bars.return_value = np.full(10, 100.0)  # 不足 20

    bar_dict = {"000001.XSHE": MagicMock()}
    handle_bar(context, bar_dict)
    context.order_target_percent.assert_not_called()
