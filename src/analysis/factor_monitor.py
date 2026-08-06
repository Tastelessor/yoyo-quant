"""因子生命周期监控（因子生命周期监控 Task 2）。

状态机 + 持久化 + 编排。只依赖 ``factors.registry`` + ``factors.evaluation``，
不依赖 backtest / strategies / portfolio / risk。

模块职责：
- ``run_state_machine``：t 统计量 → 因子状态（active / decaying / dead / reverse），
  带 min_sustain 防抖
- ``save_state`` / ``load_state`` / ``save_changes``：state/changes parquet 持久化
- ``run_monitor``：全因子编排（动态发现 + 尾部增量 + 全量重算）
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from factors.ops.evaluation import (
    compute_forward_returns,
    compute_ic,
    compute_rolling_ic,
    compute_rolling_ir,
    compute_rolling_tstat,
)
from factors.registry import list_factors, run_factor

#: state.parquet 长表列（date, factor, fwd_window 为唯一键）
STATE_COLS = [
    "date",
    "factor",
    "fwd_window",
    "ic",
    "rolling_ic",
    "rolling_ir",
    "t_stat",
    "state",
    "sustain_days",
]

#: changes.parquet 列（状态切换审计）
CHANGE_COLS = ["date", "factor", "fwd_window", "old_state", "new_state"]

#: 因子 lookback 保守上限（GTJA 长 lookback 因子），尾部增量重算缓冲用
LOOKBACK_MAX = 60

DEFAULT_OUTPUT_DIR = "data/audit/factor_monitor/"


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


def _candidate(t: float, t_active: float, t_decay: float) -> str:
    """单日候选状态：reverse 优先（负侧显著），其次 active，其次 decaying。"""
    if t <= -t_active:
        return "reverse"
    if t >= t_active:
        return "active"
    if t >= t_decay:
        return "decaying"
    return "dead"


def run_state_machine(
    t_series: pd.Series,
    t_active: float = 2.0,
    t_decay: float = 1.0,
    min_sustain: int = 20,
) -> pd.Series:
    """把滚动 t 统计量序列转换为因子状态序列（带防抖）。

    候选状态定义：
    - t ≤ -t_active → ``reverse``（显著反向）
    - t ≥ t_active → ``active``
    - t_decay ≤ t < t_active → ``decaying``
    - t < t_decay（含 NaN，数据不足）→ ``dead``

    防抖：候选状态须连续 ≥ ``min_sustain`` 日才切换，否则维持原状态并累计
    候选天数；候选回到当前状态时计数清零。冷启动首日直接按候选初始化。

    Parameters
    ----------
    t_series : Series
        滚动 t 统计量（``compute_rolling_tstat`` 输出）。
    t_active / t_decay : float
        状态阈值，须满足 ``t_decay < t_active``。
    min_sustain : int
        状态切换的最短持续日数，>= 1。

    Returns
    -------
    Series
        状态序列（str），index 与 ``t_series`` 一致。
    """
    if not isinstance(min_sustain, int) or min_sustain < 1:
        raise ValueError(f"min_sustain 必须为正整数，收到 {min_sustain!r}")
    if t_decay >= t_active:
        raise ValueError(f"t_decay({t_decay}) 必须小于 t_active({t_active})")

    out: list[str] = []
    current: str | None = None
    pending: str | None = None
    pending_days = 0
    for t in t_series.tolist():
        cand = _candidate(t, t_active, t_decay)
        if current is None:
            current = cand
        elif cand == current:
            pending, pending_days = None, 0
        else:
            if pending != cand:
                pending, pending_days = cand, 0
            pending_days += 1
            if pending_days >= min_sustain:
                current, pending, pending_days = cand, None, 0
        out.append(current)
    return pd.Series(out, index=t_series.index)


def _sustain_days(states: pd.Series) -> list[int]:
    """状态序列 → 当前状态已持续天数（含当日）。"""
    out: list[int] = []
    count, prev = 0, None
    for s in states:
        if s == prev:
            count += 1
        else:
            count, prev = 1, s
        out.append(count)
    return out


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def load_state(path: str | Path) -> pd.DataFrame:
    """读 state.parquet；文件不存在时返回空表（带 schema 列）。"""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=STATE_COLS)
    return pd.read_parquet(path)


def save_state(df: pd.DataFrame, path: str | Path) -> None:
    """追加写 state.parquet：与已有行按 (date, factor, fwd_window) 去重，
    同键保留新行（keep="last"）；写前备份旧文件为 ``<stem>.bak.parquet``。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.stem + ".bak.parquet"))
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset=["date", "factor", "fwd_window"], keep="last")
    df.to_parquet(path, index=False)


def save_changes(df: pd.DataFrame, path: str | Path) -> None:
    """追加写 changes.parquet（状态切换审计日志，不覆盖历史）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------


def diff_states(new_df: pd.DataFrame, old_state: pd.DataFrame) -> pd.DataFrame:
    """新行与旧 state 同键比较，返回状态发生切换的行（old_state → new_state）。"""
    if old_state is None or old_state.empty:
        return pd.DataFrame(columns=CHANGE_COLS)
    merged = new_df[["date", "factor", "fwd_window", "state"]].merge(
        old_state[["date", "factor", "fwd_window", "state"]],
        on=["date", "factor", "fwd_window"],
        suffixes=("", "_old"),
        how="left",
    )
    changed = merged[
        merged["state_old"].notna() & (merged["state"] != merged["state_old"])
    ].copy()
    return changed.rename(columns={"state_old": "old_state", "state": "new_state"})[
        CHANGE_COLS
    ]


def _assemble_rows(
    ic: pd.Series,
    rolling_ic: pd.Series,
    rolling_ir: pd.Series,
    t_stat: pd.Series,
    factor: str,
    fwd_window: int,
    old_state: pd.DataFrame,
    adopt_start: pd.Timestamp | None,
    t_active: float,
    t_decay: float,
    min_sustain: int,
) -> pd.DataFrame:
    """组装单个 (factor, fwd_window) 的状态行（STATE_COLS 长表片段）。

    增量（``adopt_start`` 非 None）时，状态机在「旧 t_stat 历史（< adopt_start）
    + 新 t_stat（>= adopt_start）」拼接序列上运行，保持防抖记忆与全量重算一致；
    只输出 date >= adopt_start 的新行。
    """
    t_df = pd.DataFrame({"date": ic.index, "t_stat": t_stat.to_numpy()})
    if adopt_start is not None:
        old_hist = old_state[
            (old_state["factor"] == factor)
            & (old_state["fwd_window"] == fwd_window)
            & (old_state["date"] < adopt_start)
        ][["date", "t_stat"]]
        t_hist = pd.concat(
            [old_hist, t_df[t_df["date"] >= adopt_start]], ignore_index=True
        ).sort_values("date")
        t_hist = t_hist.drop_duplicates("date", keep="last")
        t_series = pd.Series(t_hist["t_stat"].to_numpy(), index=t_hist["date"])
        states = run_state_machine(
            t_series, t_active=t_active, t_decay=t_decay, min_sustain=min_sustain
        )
        sustain = _sustain_days(states)
        keep_dates = t_df.loc[t_df["date"] >= adopt_start, "date"]
        state_map = dict(zip(t_hist["date"], states))
        sustain_map = dict(zip(t_hist["date"], sustain))
        return pd.DataFrame(
            {
                "date": keep_dates,
                "factor": [factor] * len(keep_dates),
                "fwd_window": [fwd_window] * len(keep_dates),
                "ic": ic.reindex(keep_dates).to_numpy(),
                "rolling_ic": rolling_ic.reindex(keep_dates).to_numpy(),
                "rolling_ir": rolling_ir.reindex(keep_dates).to_numpy(),
                "t_stat": t_stat.reindex(keep_dates).to_numpy(),
                "state": [state_map[d] for d in keep_dates],
                "sustain_days": [sustain_map[d] for d in keep_dates],
            }
        )
    states = run_state_machine(
        t_stat, t_active=t_active, t_decay=t_decay, min_sustain=min_sustain
    )
    return pd.DataFrame(
        {
            "date": ic.index,
            "factor": [factor] * len(ic),
            "fwd_window": [fwd_window] * len(ic),
            "ic": ic.to_numpy(),
            "rolling_ic": rolling_ic.to_numpy(),
            "rolling_ir": rolling_ir.to_numpy(),
            "t_stat": t_stat.to_numpy(),
            "state": states.to_numpy(),
            "sustain_days": _sustain_days(states),
        }
    )


def run_monitor(
    price_df: pd.DataFrame,
    factor_names: list[str] | None = None,
    fwd_windows: tuple[int, ...] = (5,),
    window: int = 60,
    min_sustain: int = 20,
    t_active: float = 2.0,
    t_decay: float = 1.0,
    min_obs: int = 5,
    exclude_untradable: bool = True,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    full: bool = False,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """因子生命周期监控编排：动态发现因子 → 计算 IC/滚动统计/状态 → 持久化。

    尾部增量（``full=False`` 且 state.parquet 已有数据）：读 ``last_date``，
    只重算其往前 ``window + LOOKBACK_MAX + fwd_max`` 交易日之后的数据，滚动
    窗口满（再推迟 ``window``）之后的新行覆盖旧行，更早行保留；保证与全量
    重算结果逐行一致。

    Parameters
    ----------
    price_df : DataFrame
        行情数据（date, code, close，可选 limit_up/limit_down/is_suspended）。
    factor_names : list[str] | None
        因子列表；None 时动态发现全部 single 因子（``list_factors(kind="single")``）。
    fwd_windows : tuple[int, ...]
        forward return 窗口（交易日数），默认 ``(5,)``。
    window : int
        滚动 IC/IR/t 窗口（数据行数），默认 60。
    min_sustain : int
        状态机防抖最短持续日数，默认 20。
    t_active / t_decay : float
        状态机阈值，默认 2.0 / 1.0。
    min_obs : int
        单日截面 IC 有效样本数下限，默认 5。
    exclude_untradable : bool
        评估时排除涨跌停/停牌日（不可交易日 forward return 置 NaN），默认 True。
    output_dir : str | Path
        输出目录，写 state.parquet / changes.parquet。
    full : bool
        True 时全量重算（忽略增量）；默认 False（有历史则尾部增量）。
    cache_dir / use_cache
        透传给 ``factors.registry.run_factor`` 的磁盘缓存参数。

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        (最新 state 长表（与 STATE_COLS 一致，已落盘）, 被跳过的因子列表
        （缺输入列等无法计算的因子，如 fundamental 透传因子无对应列时）。
    """
    factors = (
        list(factor_names) if factor_names is not None else list_factors(kind="single")
    )
    if not factors:
        raise ValueError("factor_names 为空且注册表中无 single 因子")
    output_dir = Path(output_dir)
    state_path = output_dir / "state.parquet"
    changes_path = output_dir / "changes.parquet"
    old_state = load_state(state_path)

    # ---- 尾部增量：确定重算数据段与采用起点 ----
    tail = price_df
    adopt_start: pd.Timestamp | None = None
    if not full and not old_state.empty:
        last_date = old_state["date"].max()
        dates = np.asarray(sorted(price_df["date"].unique()))
        if last_date in dates:
            idx = int(np.searchsorted(dates, last_date))
            fwd_max = max(fwd_windows)
            cut = idx - (window + 2 * LOOKBACK_MAX + fwd_max)
            if cut > 0:
                # 数据段：提前 window（滚动窗口满）+ 2*LOOKBACK_MAX（因子
                # lookback 缓冲）+ fwd_max（forward return 未来窗口）
                lookback_cut = pd.Timestamp(dates[max(0, cut)])
                tail = price_df[price_df["date"] >= lookback_cut]
                # 采用起点：数据段起点 + LOOKBACK_MAX（因子值稳定）+
                # window（滚动窗口满），即 last_date 往前 LOOKBACK_MAX + fwd_max
                adopt_start = pd.Timestamp(dates[idx - (LOOKBACK_MAX + fwd_max)])

    # ---- 逐因子计算 IC / 滚动统计 / 状态 ----
    rows: list[pd.DataFrame] = []
    skipped: list[str] = []
    for factor in factors:
        try:
            factor_series = run_factor(
                factor, tail, cache_dir=cache_dir, use_cache=use_cache
            )
        except KeyError as exc:
            # 缺输入列（如 fundamental 透传因子无 earnings/roe 列）→ 跳过，
            # 不中断整批；监控只针对可用行情计算的量价因子
            skipped.append(f"{factor}（缺列 {exc}）")
            continue
        fdf = tail.assign(__f__=factor_series.to_numpy())
        for w in fwd_windows:
            fwd = compute_forward_returns(
                tail, (w,), exclude_untradable=exclude_untradable
            )[w]
            ic = compute_ic(fdf, "__f__", fwd, min_obs=min_obs)
            rolling_ic = compute_rolling_ic(ic, window)
            rolling_ir = compute_rolling_ir(ic, window)
            t_stat = compute_rolling_tstat(ic, window)
            rows.append(
                _assemble_rows(
                    ic,
                    rolling_ic,
                    rolling_ir,
                    t_stat,
                    factor,
                    w,
                    old_state,
                    adopt_start,
                    t_active,
                    t_decay,
                    min_sustain,
                )
            )
    new_df = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=STATE_COLS)
    )
    save_state(new_df, state_path)
    changes = diff_states(new_df, old_state)
    if not changes.empty:
        save_changes(changes, changes_path)
    return load_state(state_path), skipped
