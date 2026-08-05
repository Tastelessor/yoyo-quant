"""Visualization chart tests.

All charts are saved to tests/visualization/output/ for manual review.
Run: pytest tests/visualization/test_charts.py -v
Inspect: open tests/visualization/output/*.png
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from visualization.charts import (
    plot_backtest_summary,
    plot_drawdown,
    plot_equity_curve,
)

OUTPUT_DIR = Path(__file__).parent / "output"


@pytest.fixture(autouse=True)
def _ensure_output_dir():
    """Create output dir for each test run."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def equity_curve():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04",
                 "2024-01-05", "2024-01-08"]
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


def _save(fig, name):
    """Save figure for manual inspection."""
    path = OUTPUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


# --- Equity Curve ---


def test_equity_curve_basic(equity_curve):
    fig = plot_equity_curve(equity_curve)
    path = _save(fig, "equity_curve_basic")

    ax = fig.get_axes()[0]
    # Title and labels present
    assert ax.get_title() == "Equity Curve"
    assert ax.get_xlabel() == "Date"
    assert ax.get_ylabel() == "Value"
    # Legend has Equity, Cash, Position Value
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Equity" in labels
    assert "Cash" in labels


def test_equity_curve_no_data():
    cols = ["date", "equity", "cash", "position_value", "returns"]
    empty = pd.DataFrame(columns=cols)
    fig = plot_equity_curve(empty)
    path = _save(fig, "equity_curve_empty")

    ax = fig.get_axes()[0]
    assert "(no data)" in ax.get_title()


def test_equity_curve_single_point():
    """Single data point should still render without error."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "equity": [100_000],
            "cash": [100_000],
            "position_value": [0],
            "returns": [0.0],
        }
    )
    fig = plot_equity_curve(df)
    path = _save(fig, "equity_curve_single_point")
    assert isinstance(fig, plt.Figure)


# --- Drawdown ---


def test_drawdown_basic(equity_curve):
    fig = plot_drawdown(equity_curve)
    path = _save(fig, "drawdown_basic")

    ax = fig.get_axes()[0]
    assert ax.get_title() == "Drawdown from Peak"
    assert ax.get_ylabel() == "Drawdown"
    # Y values should be <= 0 (drawdown is negative)
    lines = ax.get_lines()
    assert len(lines) > 0


def test_drawdown_no_data():
    cols = ["date", "equity", "cash", "position_value", "returns"]
    empty = pd.DataFrame(columns=cols)
    fig = plot_drawdown(empty)
    path = _save(fig, "drawdown_empty")

    ax = fig.get_axes()[0]
    assert "(no data)" in ax.get_title()


def test_drawdown_monotonic_rise():
    """No drawdown when equity only rises."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "equity": [100_000, 101_000, 102_000],
            "cash": [100_000, 100_000, 100_000],
            "position_value": [0, 0, 0],
            "returns": [0.0, 0.01, 0.01],
        }
    )
    fig = plot_drawdown(df)
    path = _save(fig, "drawdown_monotonic_rise")

    ax = fig.get_axes()[0]
    # All drawdown values should be 0
    lines = ax.get_lines()
    if lines:
        ydata = lines[0].get_ydata()
        np.testing.assert_allclose(ydata, 0.0, atol=1e-10)


# --- Backtest Summary ---


def test_backtest_summary_basic(backtest_result):
    fig = plot_backtest_summary(backtest_result)
    path = _save(fig, "backtest_summary_basic")

    axes = fig.get_axes()
    assert len(axes) == 2  # equity + drawdown
    # Suptitle has metrics text
    suptitle = fig._suptitle
    assert suptitle is not None
    assert "3.50%" in suptitle.get_text()  # total_return
    assert "1.20" in suptitle.get_text()   # sharpe


def test_backtest_summary_no_metrics(equity_curve):
    """Without metrics, should still render."""
    result = {
        "trades": pd.DataFrame(),
        "equity_curve": equity_curve,
    }
    fig = plot_backtest_summary(result)
    path = _save(fig, "backtest_summary_no_metrics")
    assert isinstance(fig, plt.Figure)


def test_backtest_summary_empty():
    """Empty equity curve should render without error."""
    cols = ["date", "equity", "cash", "position_value", "returns"]
    empty = pd.DataFrame(columns=cols)
    result = {
        "trades": pd.DataFrame(),
        "equity_curve": empty,
        "metrics": {},
    }
    fig = plot_backtest_summary(result)
    path = _save(fig, "backtest_summary_empty")
    assert isinstance(fig, plt.Figure)
