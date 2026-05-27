from unittest.mock import patch

import pandas as pd
import pytest

from src.data.universe import (
    apply_data_filters,
    apply_fundamental_filters,
    resolve_universe,
    resolve_universe_groups,
)

# --- resolve_universe: codes ---


def test_explicit_codes():
    """手动指定的代码列表应原样返回。"""
    cfg = {"codes": ["000001", "600519", "000858"]}
    result = resolve_universe(cfg)
    assert result == ["000001", "600519", "000858"]


def test_codes_deduplicated():
    """重复代码应去重。"""
    cfg = {"codes": ["000001", "600519", "000001"]}
    result = resolve_universe(cfg)
    assert result == ["000001", "600519"]


def test_empty_codes():
    """空列表应返回空列表。"""
    cfg = {"codes": []}
    result = resolve_universe(cfg)
    assert result == []


def test_missing_codes_and_index():
    """无 codes 无 index 应返回空列表。"""
    cfg = {}
    result = resolve_universe(cfg)
    assert result == []


# --- resolve_universe: filters ---


def test_filter_exclude_st():
    """exclude_st 应移除 ST 股票。"""
    cfg = {
        "codes": ["000001", "600519", "000858"],
        "filters": {"exclude_st": True},
    }
    st_list = ["000858"]
    result = resolve_universe(cfg, st_codes=st_list)
    assert "000858" not in result
    assert "000001" in result
    assert "600519" in result


def test_filter_exclude_st_empty_list():
    """空 ST 列表不应移除任何代码。"""
    cfg = {
        "codes": ["000001", "600519"],
        "filters": {"exclude_st": True},
    }
    result = resolve_universe(cfg, st_codes=[])
    assert result == ["000001", "600519"]


def test_filter_not_applied_when_false():
    """exclude_st 为 false 时不应过滤。"""
    cfg = {
        "codes": ["000001", "000858"],
        "filters": {"exclude_st": False},
    }
    result = resolve_universe(cfg, st_codes=["000858"])
    assert "000858" in result


def test_no_filters_section():
    """没有 filters 字段时应返回全部代码。"""
    cfg = {"codes": ["000001", "600519"]}
    result = resolve_universe(cfg)
    assert result == ["000001", "600519"]


# --- apply_data_filters ---


@pytest.fixture
def sample_data():
    """3只股票各5天的合成行情数据。"""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    )
    rows = []
    for code, vol_base in [
        ("000001", 10_000_000),
        ("600519", 2_000_000),
        ("000858", 300_000),
    ]:
        for i, d in enumerate(dates):
            rows.append(
                {
                    "date": d,
                    "code": code,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.0,
                    "volume": vol_base + i * 100_000,
                }
            )
    return pd.DataFrame(rows)


def test_filter_min_avg_volume(sample_data):
    """低于均量阈值的股票应被移除。"""
    cfg = {"filters": {"min_avg_volume": 5_000_000}}
    codes = ["000001", "600519", "000858"]
    result = apply_data_filters(codes, sample_data, cfg.get("filters", {}))
    assert "000001" in result  # avg ~10M
    assert "600519" not in result  # avg ~2M
    assert "000858" not in result  # avg ~300K


def test_filter_min_avg_turnover(sample_data):
    """低于成交额阈值的股票应被移除。"""
    cfg = {"filters": {"min_avg_turnover": 50_000_000}}
    codes = ["000001", "600519", "000858"]
    # volume * close = turnover
    # 000001: ~10M*10=100M, 600519: ~2M*10=20M, 000858: ~300K*10=3M
    result = apply_data_filters(codes, sample_data, cfg.get("filters", {}))
    assert "000001" in result
    assert "600519" not in result
    assert "000858" not in result


def test_filter_combined(sample_data):
    """多个过滤条件应同时生效。"""
    cfg = {"filters": {"min_avg_volume": 5_000_000, "min_avg_turnover": 50_000_000}}
    codes = ["000001", "600519", "000858"]
    result = apply_data_filters(codes, sample_data, cfg.get("filters", {}))
    assert result == ["000001"]


def test_filter_no_data_filters():
    """无过滤条件时应返回全部代码。"""
    codes = ["000001", "600519"]
    result = apply_data_filters(codes, sample_data, {})
    assert result == ["000001", "600519"]


def test_filter_empty_data():
    """空数据应返回全部代码（无法过滤）。"""
    cfg = {"filters": {"min_avg_volume": 5_000_000}}
    codes = ["000001", "600519"]
    empty_data = pd.DataFrame(
        columns=["date", "code", "open", "high", "low", "close", "volume"]
    )
    result = apply_data_filters(codes, empty_data, cfg.get("filters", {}))
    assert result == ["000001", "600519"]


def test_filter_preserves_order(sample_data):
    """过滤后应保持原始顺序。"""
    cfg = {"filters": {"min_avg_volume": 5_000_000}}
    codes = ["000858", "000001", "600519"]
    result = apply_data_filters(codes, sample_data, cfg.get("filters", {}))
    assert result == ["000001"]


# --- resolve_universe_groups ---


def test_resolve_groups_basic():
    """应正确解析命名分组。"""
    cfg = {
        "universe_groups": {
            "银行": {"codes": ["601939", "601398"]},
            "科技": {"codes": ["688981", "688256"]},
        }
    }
    result = resolve_universe_groups(cfg)
    assert result == {
        "银行": ["601939", "601398"],
        "科技": ["688981", "688256"],
    }


def test_resolve_groups_missing_section():
    """没有 universe_groups 字段时应返回空 dict。"""
    cfg = {"universe": {"codes": ["000001"]}}
    result = resolve_universe_groups(cfg)
    assert result == {}


def test_resolve_groups_empty_config():
    """空配置应返回空 dict。"""
    result = resolve_universe_groups({})
    assert result == {}


def test_resolve_groups_empty_groups():
    """universe_groups 为空时应返回空 dict。"""
    cfg = {"universe_groups": {}}
    result = resolve_universe_groups(cfg)
    assert result == {}


def test_resolve_groups_single_group():
    """只有一个分组时应正确解析。"""
    cfg = {
        "universe_groups": {
            "消费": {"codes": ["600519", "000858", "000568"]},
        }
    }
    result = resolve_universe_groups(cfg)
    assert result == {"消费": ["600519", "000858", "000568"]}


# --- resolve_universe: source=index ---


def test_resolve_universe_from_index_source():
    """source=index 应从 fetch_index_constituents 获取代码。"""
    cfg = {
        "source": "index",
        "index_code": "000905.SH",
        "fetch_date": "2026-05-23",
    }
    with patch(
        "src.data.fetcher.fetch_index_constituents", return_value=["000001", "600519"]
    ):
        result = resolve_universe(cfg)
    assert result == ["000001", "600519"]


def test_resolve_universe_index_source_with_st_filter():
    """source=index 应正确过滤 ST 股票。"""
    cfg = {
        "source": "index",
        "index_code": "000905.SH",
        "fetch_date": "2026-05-23",
        "filters": {"exclude_st": True},
    }
    with patch(
        "src.data.fetcher.fetch_index_constituents", return_value=["000001", "000858"]
    ):
        result = resolve_universe(cfg, st_codes=["000858"])
    assert result == ["000001"]


def test_resolve_universe_index_source_passes_params():
    """source=index 应正确传递 index_code 和 date 参数。"""
    cfg = {
        "source": "index",
        "index_code": "000905.SH",
        "fetch_date": "2026-05-23",
    }
    with patch("src.data.fetcher.fetch_index_constituents", return_value=[]) as mock:
        resolve_universe(cfg)
    mock.assert_called_once_with("000905.SH", date="2026-05-23")


def test_resolve_universe_static_codes_still_works():
    """静态 codes 列表应保持原有行为。"""
    cfg = {"codes": ["000001", "600519", "000858"]}
    result = resolve_universe(cfg)
    assert result == ["000001", "600519", "000858"]


def test_resolve_universe_index_source_deduplicates():
    """source=index 返回重复代码时应去重。"""
    cfg = {
        "source": "index",
        "index_code": "000905.SH",
        "fetch_date": "2026-05-23",
    }
    with patch(
        "src.data.fetcher.fetch_index_constituents",
        return_value=["000001", "000001", "600519"],
    ):
        result = resolve_universe(cfg)
    assert result == ["000001", "600519"]


# --- apply_fundamental_filters ---


@pytest.fixture
def fundamentals():
    """基本面数据。"""
    return pd.DataFrame(
        {
            "code": ["000001", "600519", "000858", "300750"],
            "pe": [5.5, 30.0, 25.0, -10.0],
            "pb": [0.6, 10.0, 8.0, 5.0],
            "total_mv": [200.0, 2000.0, 500.0, 80.0],
        }
    )


def test_filter_min_market_cap(fundamentals):
    """低于市值阈值的股票应被移除。"""
    codes = ["000001", "600519", "000858", "300750"]
    result = apply_fundamental_filters(codes, fundamentals, {"min_market_cap": 100})
    assert "000001" in result  # 200 亿
    assert "600519" in result  # 2000 亿
    assert "000858" in result  # 500 亿
    assert "300750" not in result  # 80 亿


def test_filter_min_pe(fundamentals):
    """PE 低于阈值的股票应被移除。"""
    codes = ["000001", "600519", "000858", "300750"]
    result = apply_fundamental_filters(codes, fundamentals, {"min_pe": 0})
    assert "300750" not in result  # PE = -10 (亏损)


def test_filter_max_pe(fundamentals):
    """PE 高于阈值的股票应被移除。"""
    codes = ["000001", "600519", "000858", "300750"]
    result = apply_fundamental_filters(codes, fundamentals, {"max_pe": 20})
    assert "000001" in result  # PE = 5.5
    assert "600519" not in result  # PE = 30


def test_fundamental_filter_combined(fundamentals):
    """多个过滤条件应同时生效。"""
    codes = ["000001", "600519", "000858", "300750"]
    result = apply_fundamental_filters(
        codes, fundamentals, {"min_market_cap": 100, "min_pe": 0, "max_pe": 50}
    )
    assert result == ["000001", "600519", "000858"]


def test_fundamental_filter_preserves_order(fundamentals):
    """过滤后应保持原始顺序。"""
    codes = ["300750", "000858", "600519", "000001"]
    result = apply_fundamental_filters(codes, fundamentals, {"min_market_cap": 100})
    assert result == ["000858", "600519", "000001"]


def test_filter_empty_fundamentals():
    """空基本面数据应返回全部代码。"""
    codes = ["000001", "600519"]
    result = apply_fundamental_filters(codes, pd.DataFrame(), {"min_market_cap": 100})
    assert result == ["000001", "600519"]


def test_resolve_universe_all_source():
    """source=all 应从 fetch_all_stocks + fetch_fundamentals 获取代码。"""
    cfg = {
        "source": "all",
        "fetch_date": "2026-05-22",
        "filters": {"min_market_cap": 100, "min_pe": 0},
    }
    stocks_df = pd.DataFrame({"code": ["000001", "600519", "000858"]})
    fund_df = pd.DataFrame(
        {
            "code": ["000001", "600519", "000858"],
            "pe": [5.0, 30.0, -1.0],
            "total_mv": [200.0, 2000.0, 500.0],
        }
    )
    with (
        patch("src.data.fetcher.fetch_all_stocks", return_value=stocks_df),
        patch("src.data.fetcher.fetch_fundamentals", return_value=fund_df),
    ):
        result = resolve_universe(cfg)
    assert "000001" in result
    assert "600519" in result
    assert "000858" not in result  # PE < 0
