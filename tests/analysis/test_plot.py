import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from analysis.plot import (
    plot_bootstrap_null,
    plot_factor_health_heatmap,
    plot_factor_lifecycle,
    plot_oos_winrate,
    plot_sweep_heatmap,
    plot_sweep_metrics,
)


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
    fig = plot_sweep_metrics(
        sweep_results, ["window"], metrics=["sharpe_ratio", "win_rate"]
    )
    import matplotlib.pyplot as plt

    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_metrics_two_params(sweep_results):
    """应支持双参数 X 轴。"""
    fig = plot_sweep_metrics(sweep_results, ["window", "num_std"])
    import matplotlib.pyplot as plt

    assert isinstance(fig, plt.Figure)
    plt.close(fig)


# --- plot_factor_lifecycle ---


def _lifecycle_df(n: int = 120, seed: int = 0) -> pd.DataFrame:
    """构造 (date, rolling_ir, t_stat, state) 长表切片。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n)
    n1, n2 = int(n * 0.4), int(n * 0.3)
    states = ["active"] * n1 + ["decaying"] * n2 + ["dead"] * (n - n1 - n2)
    return pd.DataFrame(
        {
            "date": dates,
            "rolling_ir": rng.normal(0.4, 0.2, n),
            "t_stat": rng.normal(1.0, 1.0, n),
            "state": states,
        }
    )


def test_lifecycle_returns_figure():
    """构造小表调用，断言返回 Figure、不抛错。"""
    import matplotlib.pyplot as plt

    fig = plot_factor_lifecycle(_lifecycle_df())
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_lifecycle_all_states():
    """四种状态都有时正常画图（reverse 段着色不抛错）。"""
    import matplotlib.pyplot as plt

    df = _lifecycle_df(120)
    df["state"] = ["active", "decaying", "dead", "reverse"] * 30
    fig = plot_factor_lifecycle(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_lifecycle_single_state_only_lines():
    """无状态转换：只画参考线，不抛错。"""
    import matplotlib.pyplot as plt

    df = _lifecycle_df()
    df["state"] = "active"
    fig = plot_factor_lifecycle(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_lifecycle_empty_state_column_value():
    """state 含未知值（如 NaN）时不抛错。"""
    import matplotlib.pyplot as plt

    df = _lifecycle_df()
    df.loc[10:20, "state"] = "unknown"
    fig = plot_factor_lifecycle(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


# --- plot_factor_health_heatmap ---


def _multi_factor_df() -> pd.DataFrame:
    """两个因子 × 两个 forward 窗口的小表。"""
    frames = []
    for f, fw in (("fa", 5), ("fa", 20), ("fb", 5)):
        sub = _lifecycle_df(n=60, seed=hash(f + str(fw)) % 1000)
        sub["factor"] = f
        sub["fwd_window"] = fw
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


def test_health_heatmap_returns_figure():
    import matplotlib.pyplot as plt

    fig = plot_factor_health_heatmap(_multi_factor_df())
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_health_heatmap_missing_values():
    """部分日期缺失（NaN）不抛错。"""
    import matplotlib.pyplot as plt

    df = _multi_factor_df()
    df.loc[df["date"] > "2024-02-15", "rolling_ir"] = np.nan
    fig = plot_factor_health_heatmap(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


# --- plot_oos_winrate / plot_bootstrap_null（Phase B）---


def test_plot_oos_winrate(tmp_path):
    import pandas as pd

    per = pd.DataFrame(
        {
            "period_idx": [0, 1, 2],
            "selected": [4, 4, 0],
            "win_rate": [0.75, 0.5, np.nan],
        }
    )
    fig = plot_oos_winrate(per)
    ax = fig.axes[0]
    assert len(ax.patches) == 2  # 无入选期不画条
    assert ax.get_xlabel() == "period_idx"
    fig.savefig(tmp_path / "w.png")


def test_plot_bootstrap_null(tmp_path):
    fig = plot_bootstrap_null(["f1", "f2"], [4.5, 2.8], [2.1, 3.3])
    ax = fig.axes[0]
    assert len(ax.patches) == 2
    assert ax.get_ylabel() == "|train_t|"
    fig.savefig(tmp_path / "b.png")
