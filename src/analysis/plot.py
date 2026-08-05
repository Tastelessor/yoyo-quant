"""参数敏感性分析可视化：热力图 + 指标柱状图；因子生命周期时序图 + 健康度热力图。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

#: 因子状态 → 背景色带颜色（active 绿 / decaying 黄 / dead 红 / reverse 灰蓝）
_STATE_COLORS = {
    "active": "#2ca02c",
    "decaying": "#ffd700",
    "dead": "#d62728",
    "reverse": "#7f8c8d",
}


def plot_sweep_heatmap(
    results: pd.DataFrame,
    x_param: str,
    y_param: str,
    metric: str = "sharpe_ratio",
    title: str | None = None,
) -> plt.Figure:
    """画双参数热力图。

    Parameters
    ----------
    results : DataFrame
        run_sweep 的输出，必须包含 x_param, y_param, metric 三列。
    x_param : str
        X 轴参数名。
    y_param : str
        Y 轴参数名。
    metric : str
        热力图颜色映射的指标名。
    title : str | None
        图表标题。

    Returns
    -------
    Figure
    """
    pivot = results.pivot_table(index=y_param, columns=x_param, values=metric)

    fig, ax = plt.subplots(figsize=(8, 6))

    # 用百分位数截断异常值，避免颜色标尺被极端值压垮
    valid = pivot.values[~np.isnan(pivot.values)]
    if len(valid) > 0:
        vmin = float(np.percentile(valid, 5))
        vmax = float(np.percentile(valid, 95))
        # 保证对称（以 0 为中心），方便比较正负
        abs_max = max(abs(vmin), abs(vmax))
        vmin, vmax = -abs_max, abs_max
    else:
        vmin, vmax = -1, 1

    im = ax.imshow(
        pivot.values,
        aspect="auto",
        cmap="RdYlGn",
        origin="lower",
        vmin=vmin,
        vmax=vmax,
    )

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel(x_param)
    ax.set_ylabel(y_param)
    ax.set_title(title or f"{metric} by {x_param} vs {y_param}")

    # 在每个格子上标注数值，根据背景亮度自动选黑/白文字
    norm = im.norm
    cmap = im.get_cmap()
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                # 取该格子对应的背景色，计算亮度
                rgba = cmap(norm(val))
                luminance = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                text_color = "white" if luminance < 0.5 else "black"
                # 格式：极端值截断显示，正常值保留两位小数
                if abs(val) >= 1e6:
                    label = f"{val:.1e}"
                elif abs(val) >= 100:
                    label = f"{val:.0f}"
                elif abs(val) < 0.01 and val != 0:
                    label = f"{val:.2e}"
                else:
                    label = f"{val:.2f}"
                ax.text(j, i, label, ha="center", va="center",
                        color=text_color, fontsize=8)

    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def plot_sweep_metrics(
    results: pd.DataFrame,
    params: list[str],
    metrics: list[str] | None = None,
    title: str | None = None,
) -> plt.Figure:
    """画参数 vs 多指标的折线/柱状图。

    Parameters
    ----------
    results : DataFrame
        run_sweep 的输出。
    params : list[str]
        X 轴参数名（支持 1-2 个）。
    metrics : list[str] | None
        要画的指标列表，默认 ["total_return", "sharpe_ratio", "max_drawdown"]。
    title : str | None
        图表标题。

    Returns
    -------
    Figure
    """
    if metrics is None:
        metrics = ["total_return", "sharpe_ratio", "max_drawdown"]

    n_metrics = len(metrics)
    fig, axes = plt.subplots(1, n_metrics, figsize=(5 * n_metrics, 4), squeeze=False)
    axes = axes[0]

    label = " × ".join(params) if len(params) > 1 else params[0]
    sorted_df = results.sort_values(params[0]).reset_index(drop=True)

    for i, metric in enumerate(metrics):
        ax = axes[i]
        ax.bar(range(len(sorted_df)), sorted_df[metric], color="steelblue", alpha=0.7)
        ax.set_xticks(range(len(sorted_df)))
        ax.set_xticklabels(
            [
                f"{row[params[0]]}"
                if len(params) == 1
                else f"{row[params[0]]}×{row[params[1]]}"
                for _, row in sorted_df.iterrows()
            ],
            rotation=45,
            fontsize=7,
        )
        ax.set_xlabel(label)
        ax.set_ylabel(metric)
        ax.set_title(metric)
        ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)

    if title:
        fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    return fig


def _contiguous_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    """布尔掩码 → 连续 True 段的 (start, end) 索引区间列表（含端）。"""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    breaks = np.where(np.diff(idx) > 1)[0]
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks], [idx[-1]]])
    return list(zip(starts, ends))


def plot_factor_lifecycle(
    data: pd.DataFrame,
    *,
    t_active: float = 2.0,
    t_decay: float = 1.0,
    ir_active_line: float = 0.7,
    ir_dead_line: float = 0.3,
    title: str | None = None,
) -> plt.Figure:
    """画单个 (factor, fwd_window) 的生命周期双轴时序图。

    - 左轴：滚动 IR（蓝线）+ ``ir_active_line`` / ``ir_dead_line`` 参考线
    - 右轴：t 统计量（黑线）+ ±``t_active`` / ±``t_decay`` 判定线
    - 背景色带：按 state 着色（active 绿 / decaying 黄 / dead 红 / reverse 灰蓝）

    Parameters
    ----------
    data : DataFrame
        长表切片，须含 date / rolling_ir / t_stat / state 四列
        （单 factor × fwd_window）。
    t_active, t_decay : float
        状态机判定阈值（右轴参考线）。
    ir_active_line, ir_dead_line : float
        滚动 IR 经验参考线（左轴）。
    title : str | None
        图表标题。

    Returns
    -------
    Figure
    """
    df = data.sort_values("date").reset_index(drop=True)
    x = df["date"]
    fig, ax_ir = plt.subplots(figsize=(12, 5))
    ax_t = ax_ir.twinx()

    # 背景色带：按状态画连续段
    for state, color in _STATE_COLORS.items():
        mask = (df["state"] == state).to_numpy()
        for start, end in _contiguous_segments(mask):
            ax_ir.axvspan(x.iloc[start], x.iloc[end], color=color, alpha=0.15)

    ax_ir.plot(x, df["rolling_ir"], color="steelblue", linewidth=1, label="rolling IR")
    ax_ir.axhline(ir_active_line, color="steelblue", linestyle="--", linewidth=0.8)
    ax_ir.axhline(ir_dead_line, color="steelblue", linestyle=":", linewidth=0.8)
    ax_ir.set_ylabel("rolling IR")

    ax_t.plot(x, df["t_stat"], color="black", linewidth=1, label="t-stat")
    for line in (t_active, -t_active, t_decay, -t_decay):
        ax_t.axhline(line, color="gray", linestyle="--", linewidth=0.6)
    ax_t.set_ylabel("t-stat")

    ax_ir.set_xlabel("date")
    ax_ir.set_title(title or "factor lifecycle")
    fig.tight_layout()
    return fig


def plot_factor_health_heatmap(
    data: pd.DataFrame,
    *,
    value: str = "rolling_ir",
    title: str | None = None,
) -> plt.Figure:
    """画全因子健康度热力图：x=时间，y=因子（factor×fwd_window），颜色=滚动 IR。

    颜色映射 RdYlGn 且以 0 为中心对称截断（取 5/95 百分位绝对值较大者），
    与 ``plot_sweep_heatmap`` 的 vmin/vmax 处理一致；缺失值显示为浅灰。

    Parameters
    ----------
    data : DataFrame
        长表，须含 factor / fwd_window / date 与 ``value`` 列。
    value : str
        颜色映射列，默认 rolling_ir。
    title : str | None
        图表标题。

    Returns
    -------
    Figure
    """
    df = data.copy()
    df["key"] = df["factor"] + "/fwd" + df["fwd_window"].astype(str)
    pivot = df.pivot_table(index="key", columns="date", values=value)

    valid = pivot.values[~np.isnan(pivot.values)]
    if len(valid) > 0:
        p5 = abs(float(np.percentile(valid, 5)))
        p95 = abs(float(np.percentile(valid, 95)))
        vmax = max(p5, p95)
    else:
        vmax = 1.0
    if vmax <= 0:
        vmax = 1.0

    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#f0f0f0")

    fig, ax = plt.subplots(figsize=(14, max(4, 0.4 * len(pivot.index))))
    im = ax.imshow(
        pivot.values, aspect="auto", cmap=cmap, vmin=-vmax, vmax=vmax, origin="lower"
    )
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    n = len(pivot.columns)
    step = max(1, n // 10)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [str(pivot.columns[i].date()) for i in ticks], rotation=45, ha="right"
    )
    ax.set_xlabel("date")
    ax.set_title(title or f"factor health ({value})")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig
