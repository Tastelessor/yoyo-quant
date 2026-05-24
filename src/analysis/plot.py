"""参数敏感性分析可视化：热力图 + 指标柱状图。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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
            [f"{row[params[0]]}" if len(params) == 1 else f"{row[params[0]]}×{row[params[1]]}"
             for _, row in sorted_df.iterrows()],
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
