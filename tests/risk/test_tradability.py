import pandas as pd
import pytest

from data.filters import detect_limit_price, detect_suspension
from risk.rules import RuleContext
from risk.tradability import T1Rule, TradabilityRule, enforce_t1, filter_tradable


@pytest.fixture
def ohlcv_data():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
            ),
            "code": "000001.SZ",
            "open": [10.0, 11.0, 12.1, 10.0, 10.0],
            "high": [11.0, 12.1, 13.31, 10.0, 10.5],
            "low": [10.0, 11.0, 12.1, 9.0, 9.5],
            "close": [11.0, 12.1, 13.31, 9.0, 10.0],
            "volume": [1_000_000, 1_200_000, 500_000, 800_000, 0],
        }
    )


@pytest.fixture
def annotated_market(ohlcv_data):
    """data 层输出的已标注行情数据。"""
    df = detect_limit_price(ohlcv_data)
    df = detect_suspension(df)
    return df


# --- filter_tradable ---


def test_filter_buy_on_limit_up(annotated_market):
    """涨停日买入信号应被过滤。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-03"]),
            "code": "000001.SZ",
            "signal": [1],
            "confidence": [0.8],
        }
    )
    result = filter_tradable(annotated_market, signals)
    assert result["signal"].iloc[0] == 0


def test_filter_sell_on_limit_down(annotated_market):
    """跌停日卖出信号应被过滤。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05"]),
            "code": "000001.SZ",
            "signal": [-1],
            "confidence": [0.8],
        }
    )
    result = filter_tradable(annotated_market, signals)
    assert result["signal"].iloc[0] == 0


def test_filter_any_signal_on_suspension(annotated_market):
    """停牌日任何信号应被过滤。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-08"]),
            "code": "000001.SZ",
            "signal": [1],
            "confidence": [0.8],
        }
    )
    result = filter_tradable(annotated_market, signals)
    assert result["signal"].iloc[0] == 0


def test_filter_pass_normal_signal(annotated_market):
    """正常交易日信号不应被过滤。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-04"]),
            "code": "000001.SZ",
            "signal": [-1],
            "confidence": [0.6],
        }
    )
    result = filter_tradable(annotated_market, signals)
    # 12.1 → 12.1 不涨不跌，但 500_000 成交量不为 0 → 不停牌
    # signal=-1 且非跌停 → 保留
    assert result["signal"].iloc[0] == -1


# --- enforce_t1 ---


def test_t1_same_day_buy_wins():
    """同日买入和卖出信号，买入优先。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "code": "000001.SZ",
            "signal": [1, -1],
            "confidence": [0.8, 0.7],
        }
    )
    result = enforce_t1(signals)
    # 买入保留，卖出置 0
    assert result[result["signal"] == 1].shape[0] == 1
    assert result[result["signal"] == 0].shape[0] == 1


def test_t1_no_conflict():
    """无冲突信号应原样返回。"""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": "000001.SZ",
            "signal": [1, -1],
            "confidence": [0.8, 0.7],
        }
    )
    result = enforce_t1(signals)
    assert list(result["signal"]) == [1, -1]


# --- TradabilityRule (Rule ABC wrapper) ---


def test_tradability_rule_name_and_priority():
    rule = TradabilityRule()
    assert rule.name == "tradability"
    assert rule.priority == 200


def test_tradability_rule_filters_limit_up(annotated_market):
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-03"]),
            "code": "000001.SZ",
            "signal": [1],
            "confidence": [0.8],
        }
    )
    ctx = RuleContext(
        signals=signals,
        positions=pd.DataFrame(),
        market_data=annotated_market,
    )
    rule = TradabilityRule()
    result = rule.apply(ctx)
    assert result.signals["signal"].iloc[0] == 0


def test_tradability_rule_returns_rule_context(annotated_market):
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-04"]),
            "code": "000001.SZ",
            "signal": [-1],
            "confidence": [0.6],
        }
    )
    ctx = RuleContext(
        signals=signals,
        positions=pd.DataFrame(),
        market_data=annotated_market,
    )
    rule = TradabilityRule()
    result = rule.apply(ctx)
    assert isinstance(result, RuleContext)


# --- T1Rule (Rule ABC wrapper) ---


def test_t1_rule_name_and_priority():
    rule = T1Rule()
    assert rule.name == "t1"
    assert rule.priority == 210


def test_t1_rule_same_day_buy_wins():
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "code": "000001.SZ",
            "signal": [1, -1],
            "confidence": [0.8, 0.7],
        }
    )
    ctx = RuleContext(
        signals=signals,
        positions=pd.DataFrame(),
        market_data=pd.DataFrame(),
    )
    rule = T1Rule()
    result = rule.apply(ctx)
    assert result.signals[result.signals["signal"] == 1].shape[0] == 1
    assert result.signals[result.signals["signal"] == 0].shape[0] == 1
