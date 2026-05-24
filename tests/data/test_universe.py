import pandas as pd
import pytest

from src.data.universe import apply_data_filters, resolve_universe


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
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
    rows = []
    for code, vol_base in [("000001", 10_000_000), ("600519", 2_000_000), ("000858", 300_000)]:
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
    # volume * close = turnover; 000001: ~10M*10=100M, 600519: ~2M*10=20M, 000858: ~300K*10=3M
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
    empty_data = pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])
    result = apply_data_filters(codes, empty_data, cfg.get("filters", {}))
    assert result == ["000001", "600519"]


def test_filter_preserves_order(sample_data):
    """过滤后应保持原始顺序。"""
    cfg = {"filters": {"min_avg_volume": 5_000_000}}
    codes = ["000858", "000001", "600519"]
    result = apply_data_filters(codes, sample_data, cfg.get("filters", {}))
    assert result == ["000001"]
