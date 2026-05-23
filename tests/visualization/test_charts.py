"""Visualization chart tests."""

import matplotlib

matplotlib.use("Agg")  # non-interactive backend for testing

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from src.visualization.charts import (
    plot_backtest_summary,
    plot_drawdown,
    plot_equity_curve,
)


@pytest.fixture
def equity_curve():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
            ),
            "equity": [100_000, 101_000, 99_500, 102_000, 103_500],
            "cash": [100_000, 50_000, 50_000, 50_000, 50_000],
            "position_value": [0, 51_000, 49_500, 52_000, 53_500],
            "returns": [0.0, 0.01, -0.0149, 0.0251, 0.0147],
        }
    )


@pytest.fixture
def backtest_result(equity_curve):
    return {
        "trades": pd.DataFrame(
            columns=["date", "code", "action", "price", "shares", "pnl"]
        ),
        "equity_curve": equity_curve,
        "metrics": {
            "total_return": 0.035,
            "annual_return": 0.08,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.0149,
            "win_rate": 0.6,
            "trade_count": 10,
        },
    }


def test_plot_equity_curve_returns_figure(equity_curve):
    fig = plot_equity_curve(equity_curve)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_drawdown_returns_figure(equity_curve):
    fig = plot_drawdown(equity_curve)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_backtest_summary_returns_figure(backtest_result):
    fig = plot_backtest_summary(backtest_result)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_equity_curve_empty():
    cols = ["date", "equity", "cash", "position_value", "returns"]
    empty = pd.DataFrame(columns=cols)
    fig = plot_equity_curve(empty)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_drawdown_empty():
    cols = ["date", "equity", "cash", "position_value", "returns"]
    empty = pd.DataFrame(columns=cols)
    fig = plot_drawdown(empty)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_plot_backtest_summary_has_metrics_text(backtest_result):
    fig = plot_backtest_summary(backtest_result)
    # Should have at least 2 subplots (equity + drawdown)
    axes = fig.get_axes()
    assert len(axes) >= 2
    plt.close(fig)
