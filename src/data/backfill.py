"""data/backfill.py — 通用批量拉取调度（多轮扫描 + 断点续拉）。

沉淀 Phase 1 Task 9 的真实拉取模式（.superpowers/fetch_basic.py /
fetch_moneyflow.py）：每轮遍历全部交易日，单日函数内部自行处理缓存命中/续拉，
失败日期收集后进入下一轮（轮间 round_pause 等待代理/限频恢复）；成功日期不再
进入下一轮。Phase 2-5 各数据域（limit_market / report_rc 等）复用同一调度。

只复用 data 层既有接口（fetch_trade_dates / fetch_fundamentals /
fetch_moneyflow_by_date），不新增外部依赖。
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pandas as pd

from data.fetcher import fetch_fundamentals
from data.moneyflow import fetch_moneyflow_by_date
from data.trade_calendar import fetch_trade_dates


def backfill_range(
    fetch_day: Callable[[str], pd.DataFrame],
    start: str,
    end: str,
    *,
    max_rounds: int = 40,
    round_pause: float = 60.0,
) -> dict:
    """多轮扫描批量拉取：遍历交易日，单日函数内部自行处理缓存命中/续拉。

    Parameters
    ----------
    fetch_day : Callable[[str], pd.DataFrame]
        单日拉取函数（"YYYY-MM-DD" → DataFrame）；抛异常或返回空 DataFrame
        均记为失败，进入下一轮重试。
    start, end : str
        日期范围闭区间 "YYYY-MM-DD"（透传 fetch_trade_dates）。
    max_rounds : int
        最大轮数；达到后返回时仍失败的日期进 failed。
    round_pause : float
        轮间 sleep 秒数（默认 60，等代理/限频恢复）；0 不 sleep。

    Returns
    -------
    dict
        {"total": int, "success": int, "failed": list[str]}
    """
    dates = [str(d.date()) for d in fetch_trade_dates(start, end)]
    total = len(dates)
    success = 0
    pending = dates
    for _ in range(max_rounds):
        still: list[str] = []
        for d in pending:
            try:
                df = fetch_day(d)
            except Exception:  # noqa: BLE001 - 网络/限频等瞬态故障，延后重试
                still.append(d)
                continue
            if df is None or df.empty:
                # 单日拉不到数据（接口空返回）同样视为失败，下轮再试
                still.append(d)
                continue
            success += 1
        pending = still
        if not pending:
            break
        if round_pause > 0:
            time.sleep(round_pause)
    return {"total": total, "success": success, "failed": pending}


def fetch_fundamentals_range(
    start: str,
    end: str,
    *,
    max_rounds: int = 40,
    round_pause: float = 60.0,
) -> dict:
    """daily_basic 批量拉取（复用 data.fetcher.fetch_fundamentals，断点续拉）。

    Parameters
    ----------
    start, end : str
        日期范围闭区间 "YYYY-MM-DD"。
    max_rounds : int
        最大轮数（透传 backfill_range）。
    round_pause : float
        轮间 sleep 秒数（透传 backfill_range）。

    Returns
    -------
    dict
        {"total": int, "success": int, "failed": list[str]}，见 backfill_range。
    """
    return backfill_range(
        fetch_fundamentals,
        start,
        end,
        max_rounds=max_rounds,
        round_pause=round_pause,
    )


def fetch_moneyflow_range(
    start: str,
    end: str,
    *,
    max_rounds: int = 40,
    round_pause: float = 60.0,
) -> dict:
    """moneyflow 批量拉取（复用 data.moneyflow.fetch_moneyflow_by_date，断点续拉）。

    Parameters
    ----------
    start, end : str
        日期范围闭区间 "YYYY-MM-DD"。
    max_rounds : int
        最大轮数（透传 backfill_range）。
    round_pause : float
        轮间 sleep 秒数（透传 backfill_range）。

    Returns
    -------
    dict
        {"total": int, "success": int, "failed": list[str]}，见 backfill_range。
    """
    return backfill_range(
        fetch_moneyflow_by_date,
        start,
        end,
        max_rounds=max_rounds,
        round_pause=round_pause,
    )
