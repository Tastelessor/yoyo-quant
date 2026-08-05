import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

from analysis.plot import plot_sweep_heatmap, plot_sweep_metrics


@pytest.fixture
def sweep_results():
    """模拟 sweep 结果。"""
    return pd.DataFrame(
        {
            "window": [10, 10, 20, 20],
            "num_std": [1.5, 2.0, 1.5, 2.0],
            "total_return": [0.05, 0.03, -0.02, 0.08],
            "sharpe_ratio": [0.8, 0.4, -0.3, 1.2],
            "max_drawdown": [0.10, 0.15, 0.20, 0.08],
            "win_rate": [0.55, 0.50, 0.45, 0.60],
            "trade_count": [20, 15, 25, 18],
        }
    )


# --- plot_sweep_heatmap ---


def test_heatmap_returns_figure(sweep_results):
    """应返回 matplotlib Figure。"""
    fig = plot_sweep_heatmap(sweep_results, "window", "num_std", "sharpe_ratio")
    assert isinstance(fig, type(fig).__mro__[0])  # is a Figure or subclass
    import matplotlib.pyplot as plt
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_heatmap_custom_metric(sweep_results):
    """应支持自定义指标。"""
    fig = plot_sweep_heatmap(sweep_results, "window", "num_std", "total_return")
    import matplotlib.pyplot as plt
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


# --- plot_sweep_metrics ---


def test_metrics_returns_figure(sweep_results):
    """应返回 matplotlib Figure。"""
    fig = plot_sweep_metrics(sweep_results, ["window"])
    import matplotlib.pyplot as plt
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_metrics_custom_list(sweep_results):
    """应支持自定义指标列表。"""
    fig = plot_sweep_metrics(sweep_results, ["window"], metrics=["sharpe_ratio", "win_rate"])
    import matplotlib.pyplot as plt
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_metrics_two_params(sweep_results):
    """应支持双参数 X 轴。"""
    fig = plot_sweep_metrics(sweep_results, ["window", "num_std"])
    import matplotlib.pyplot as plt
    assert isinstance(fig, plt.Figure)
    plt.close(fig)
