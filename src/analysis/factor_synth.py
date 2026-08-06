"""analysis/factor_synth.py — Phase C 编排（analysis 层）。

读 Phase A 代表因子 + monitor state + 全市场 ohlcv → 合成信号 →
与各单因子回测对比（相同参数）→ 输出信号 / 对比表 / 净值图 / summary。
只读 monitor 产物与 Phase A 产物，不重算 IC/状态/相关。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.factor_monitor import STATE_COLS
from backtest.pipeline import run_pipeline
from factors.ops.synth import (
    combine_factor_scores,
    compute_ic_weights,
    scores_to_signals,
)
from factors.registry import run_factor


def _load_state(state_path: Path) -> pd.DataFrame:
    path = Path(state_path)
    if not path.exists():
        raise FileNotFoundError(f"state 文件不存在: {path}")
    df = pd.read_parquet(path)
    if not set(STATE_COLS).issubset(df.columns):
        raise ValueError(f"state.parquet 缺少列，需要 {STATE_COLS}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _resolve_representatives(rep: list[str] | str | Path) -> list[str]:
    """把代表因子输入归一化为因子名列表。

    list 原样返回；Path/str 视为 Phase A 的 representatives.json
    （含 ``representatives`` 键，每项取 ``representative`` 字段）。
    """
    if isinstance(rep, (str, Path)):
        payload = json.loads(Path(rep).read_text(encoding="utf-8"))
        return [r["representative"] for r in payload["representatives"]]
    return list(rep)


def compare_backtests(
    signals_map: dict[str, pd.DataFrame],
    data: pd.DataFrame,
    *,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    dead_zone: float = 0.015,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """多个信号各跑一遍 run_pipeline，返回 (metrics 对比表, 净值曲线 dict)。

    Parameters
    ----------
    signals_map : dict[str, DataFrame]
        {名称: (date, code, signal, confidence)}。
    data : DataFrame
        全市场行情（run_pipeline 的可交易性过滤/价格提取/引擎数据）。

    Returns
    -------
    (compare, curves)
        compare：index=strategy，列 = metrics（total_return / annual_return /
        sharpe_ratio / max_drawdown / win_rate / trade_count / total_cost /
        cost_ratio）。
        curves：{strategy: equity_curve DataFrame(date, equity, ...)}。
    """
    rows: list[dict] = []
    curves: dict[str, pd.DataFrame] = {}
    for name, sig in signals_map.items():
        res = run_pipeline(
            sig, data, capital, max_weight=max_weight, dead_zone=dead_zone
        )
        rows.append({"strategy": name, **res["metrics"]})
        curves[name] = res["equity_curve"]
    return pd.DataFrame(rows).set_index("strategy"), curves


def run_phase_c(
    *,
    state_path: Path,
    ohlcv_path: Path,
    representatives: list[str] | str | Path,
    synth_weighting: str = "equal",
    fwd_window: int = 5,
    ic_lookback: int = 60,
    rebalance: int = 20,
    top_n: int = 10,
    bottom_n: int = 5,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    output_dir: Path | None = None,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    dead_zone: float = 0.015,
) -> dict:
    """Phase C 编排：代表因子 → 合成信号 → 与单因子对比回测。

    Parameters
    ----------
    state_path : Path
        monitor 输出的 state.parquet（STATE_COLS 长表，IC 权重用）。
    ohlcv_path : Path
        全市场行情 parquet（date/code/close/...，含状态列）。
    representatives : list[str] | Path
        代表因子名单，或 Phase A representatives.json 路径。
    synth_weighting : str
        "equal"（默认）| "ic_weighted"。
    fwd_window : int
        IC 权重取 state 中该 forward 窗口的 IC 行。
    ic_lookback : int
        IC 权重评估窗口（交易日）。
    rebalance / top_n / bottom_n
        信号生成参数（透传 scores_to_signals）。
    cache_dir / use_cache
        透传给 run_factor。
    output_dir : Path | None
        给定时写 synth_signals.parquet / backtest_compare.parquet /
        equity_compare.png / summary.json。
    capital / max_weight / dead_zone
        回测参数（所有策略一致，保证对比公平）。

    Returns
    -------
    dict
        键：signals（合成信号）/ compare（对比表）/ equity_curves /
        summary（synth_weighting / best_single / synth_sharpe /
        synth_beats_best_single 等）。
    """
    if synth_weighting not in {"equal", "ic_weighted"}:
        raise ValueError(f"synth_weighting 非法: {synth_weighting!r}")
    factors = _resolve_representatives(representatives)
    if not factors:
        raise ValueError("representatives 解析为空")

    state = _load_state(state_path)
    as_of = state["date"].max()
    data = pd.read_parquet(ohlcv_path)
    data["date"] = pd.to_datetime(data["date"])

    # 因子值：只保留 date/code + 代表因子列
    base = data[["date", "code"]].copy()
    factor_df = base.copy()
    for f in factors:
        try:
            factor_df[f] = run_factor(
                f, data, cache_dir=cache_dir, use_cache=use_cache
            ).to_numpy()
        except KeyError:
            factor_df[f] = float("nan")

    # 权重
    if synth_weighting == "equal":
        weights = None
    else:
        weights = compute_ic_weights(
            state, factors, as_of=as_of, fwd_window=fwd_window, lookback=ic_lookback
        )

    # 合成信号
    score = combine_factor_scores(factor_df, factors, weights=weights)
    synth_sig = scores_to_signals(
        factor_df, score, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n
    )

    # 单因子信号（同参数，保证对比公平）
    signals_map: dict[str, pd.DataFrame] = {"synth": synth_sig}
    for f in factors:
        if factor_df[f].notna().sum() < 2:
            continue  # 缺列/全 NaN 的因子不参与对比
        single_score = combine_factor_scores(factor_df, [f])
        signals_map[f] = scores_to_signals(
            factor_df, single_score, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n
        )

    compare, curves = compare_backtests(
        signals_map, data, capital=capital, max_weight=max_weight, dead_zone=dead_zone
    )

    synth_sharpe = float(compare.loc["synth", "sharpe_ratio"])
    singles = compare.drop(index="synth")
    best_name = singles["sharpe_ratio"].idxmax() if len(singles) > 0 else None
    best_sharpe = (
        float(singles.loc[best_name, "sharpe_ratio"]) if best_name is not None else 0.0
    )
    summary = {
        "synth_weighting": synth_weighting,
        "weights": weights,
        "representatives": factors,
        "rebalance": rebalance,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "synth_sharpe": synth_sharpe,
        "best_single": best_name,
        "best_single_sharpe": best_sharpe,
        "synth_beats_best_single": bool(synth_sharpe >= best_sharpe),
    }

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        synth_sig.to_parquet(out / "synth_signals.parquet", index=False)
        compare.to_parquet(out / "backtest_compare.parquet")
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        from analysis.plot import plot_equity_compare

        plot_equity_compare(curves).savefig(
            out / "equity_compare.png", dpi=110, bbox_inches="tight"
        )

    return {
        "signals": synth_sig,
        "compare": compare,
        "equity_curves": curves,
        "summary": summary,
    }
