"""因子清洗编排（Phase A/B/C 业务层）。

Phase A：读 monitor 的 state 长表 + 全市场 ohlcv → 候选因子 → 相关矩阵 →
聚类 → 代表因子清单。只读 monitor 产物，不重算 IC/状态。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.factor_monitor import LOOKBACK_MAX, STATE_COLS
from factors.ops.correlation import (
    cluster_redundant,
    compute_corr_matrix,
    select_representative,
)
from factors.registry import run_factor

ACTIVE_STATES = ("active", "decaying")


def _load_state(state_path: Path) -> pd.DataFrame:
    """读 state.parquet 并校验 schema；date 列规范化为 datetime64。

    注意：state.parquet 由 ``save_state`` 写盘，真实 monitor 产物的 date 为
    datetime64；但测试/手工构造的 parquet 里 date 可能是字符串列，统一在此
    转换为 datetime64，保证 ``as_of`` 返回 ``pd.Timestamp`` 且日期 mask 可比较。
    """
    path = Path(state_path)
    if not path.exists():
        raise FileNotFoundError(f"state 文件不存在: {path}")
    df = pd.read_parquet(path)
    if not set(STATE_COLS).issubset(df.columns):
        raise ValueError(f"state.parquet 缺少列，需要 {STATE_COLS}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def run_phase_a(
    *,
    state_path: Path,
    ohlcv_path: Path,
    corr_window: int = 60,
    corr_threshold: float = 0.7,
    cluster_linkage: str = "ward",
    representative_by: str = "t_stat",
    fwd_window: int = 5,
    exclude_untradable: bool = True,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    output_dir: Path | None = None,
) -> dict:
    """Phase A 编排：候选因子 → 相关矩阵 → 聚类 → 代表因子清单。

    Parameters
    ----------
    state_path : Path
        monitor 输出的 state.parquet（STATE_COLS 长表）。
    ohlcv_path : Path
        全市场行情 parquet（date/code/close/...）。
    corr_window / corr_threshold / cluster_linkage / representative_by
        透传给 correlation 纯函数（见 ``factors/ops/correlation``）。
    fwd_window : int
        取 state 中该 forward 窗口的统计行。
    exclude_untradable : bool
        预留：与 monitor 语义一致（当前 Phase A 只用因子值，无 forward return）。
    cache_dir / use_cache
        透传给 ``run_factor``。
    output_dir : Path | None
        给定时写 corr_matrix/clusters/representatives/PNG。

    Returns
    -------
    dict
        键：as_of / factors / skipped / corr_matrix / clusters / representatives。
    """
    state = _load_state(state_path)
    as_of = state["date"].max()
    mask = (
        (state["date"] == as_of)
        & (state["state"].isin(ACTIVE_STATES))
        & (state["fwd_window"] == fwd_window)
    )
    factors = sorted(state.loc[mask, "factor"].unique().tolist())

    price = pd.read_parquet(ohlcv_path)
    dates = sorted(price["date"].unique())
    cut = max(0, len(dates) - (corr_window + LOOKBACK_MAX + fwd_window))
    tail = price[price["date"] >= dates[cut]]

    values: dict[str, pd.Series] = {}
    skipped: list[str] = []
    for factor in factors:
        try:
            values[factor] = run_factor(
                factor, tail, cache_dir=cache_dir, use_cache=use_cache
            )
        except KeyError as exc:
            skipped.append(f"{factor}（缺列 {exc}）")
            continue

    keep = [f for f in factors if f in values]
    if not keep:
        # 全部候选缺列被跳过：无从计算相关/聚类，返回空结构（不写 output_dir）。
        # 上游 cluster_redundant 对空距离矩阵无守卫，编排层在此兜底。
        return {
            "as_of": as_of,
            "factors": keep,
            "skipped": skipped,
            "corr_matrix": pd.DataFrame(index=[], columns=[]),
            "clusters": pd.DataFrame(columns=["factor", "cluster_id"]),
            "representatives": pd.DataFrame(
                columns=["cluster_id", "representative", "members", "member_count"]
            ),
        }
    factor_df = tail.assign(**{f: values[f].to_numpy() for f in keep})

    corr = compute_corr_matrix(factor_df, keep, window=corr_window)
    clusters = cluster_redundant(
        corr, threshold=corr_threshold, linkage_method=cluster_linkage
    )
    latest = state[(state["date"] == as_of) & (state["fwd_window"] == fwd_window)]
    stats = (
        latest[["factor", "t_stat", "rolling_ir"]]
        .drop_duplicates("factor")
        .rename(columns={"rolling_ir": "ir"})
    )
    representatives = select_representative(clusters, stats, by=representative_by)

    result = {
        "as_of": as_of,
        "factors": keep,
        "skipped": skipped,
        "corr_matrix": corr,
        "clusters": clusters,
        "representatives": representatives,
    }
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        corr.to_parquet(out / "corr_matrix.parquet", index=True)
        clusters.to_parquet(out / "clusters.parquet", index=False)
        payload = {
            "as_of": str(as_of.date()),
            "corr_threshold": corr_threshold,
            "representative_by": representative_by,
            "representatives": representatives.to_dict("records"),
            "skipped": skipped,
        }
        (out / "representatives.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        from analysis.plot import plot_cluster_dendrogram, plot_corr_matrix

        fig = plot_corr_matrix(corr)
        fig.savefig(out / "corr_heatmap.png", dpi=110, bbox_inches="tight")
        if len(corr) > 1:
            # 1×1 相关矩阵没有聚类树（scipy linkage 对空距离矩阵抛错），跳过 dendrogram
            plot_cluster_dendrogram(corr, threshold=corr_threshold).savefig(
                out / "dendrogram.png", dpi=110, bbox_inches="tight"
            )
    return result
