"""股票池解析与过滤。

根据配置解析股票池，支持手动指定代码、ST 排除，以及基于行情数据的流动性过滤。
"""

from __future__ import annotations

import pandas as pd


def resolve_universe(
    cfg: dict,
    st_codes: list[str] | None = None,
) -> list[str]:
    """从配置解析股票池，返回去重后的代码列表。

    Parameters
    ----------
    cfg : dict
        universe 配置段，支持的字段：
        - codes: list[str]，手动指定的代码列表
        - filters.exclude_st: bool，是否排除 ST 股票
    st_codes : list[str] | None
        当前 ST 股票代码列表。exclude_st 为 True 时必须提供。

    Returns
    -------
    list[str]
        去重后的股票代码列表，保持首次出现的顺序。
    """
    codes = list(cfg.get("codes") or [])

    filters = cfg.get("filters") or {}
    if filters.get("exclude_st") and st_codes is not None:
        st_set = set(st_codes)
        codes = [c for c in codes if c not in st_set]

    # 去重，保持顺序
    seen: set[str] = set()
    deduped: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def apply_data_filters(
    codes: list[str],
    data: pd.DataFrame,
    filters: dict,
) -> list[str]:
    """对代码列表执行基于行情数据的过滤。

    Parameters
    ----------
    codes : list[str]
        待过滤的股票代码列表。
    data : DataFrame
        行情数据，必须包含 code, volume, close 列。
    filters : dict
        过滤条件：
        - min_avg_volume: float，平均成交量下限（全量数据）
        - min_avg_turnover: float，平均成交额下限（volume * close，全量数据）

    Returns
    -------
    list[str]
        过滤后的代码列表，保持原始顺序。
    """
    if not filters or data.empty:
        return codes

    # 按 code 聚合计算均量和均额
    grouped = data.groupby("code")
    avg_volume = grouped["volume"].mean()

    result = list(codes)

    min_vol = filters.get("min_avg_volume")
    if min_vol is not None:
        result = [c for c in result if c in avg_volume and avg_volume[c] >= min_vol]

    min_turnover = filters.get("min_avg_turnover")
    if min_turnover is not None:
        avg_turnover = (data["volume"] * data["close"]).groupby(data["code"]).mean()
        result = [c for c in result if c in avg_turnover and avg_turnover[c] >= min_turnover]

    return result
