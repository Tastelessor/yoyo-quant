"""Static charts for backtest visualization."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_equity_curve(eq: pd.DataFrame) -> plt.Figure:
    """Plot equity curve over time.

    Parameters
    ----------
    eq : DataFrame
        Equity curve with columns: date, equity, cash, position_value.

    Returns
    -------
    Figure
        Matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    if eq.empty:
        ax.set_title("Equity Curve (no data)")
        return fig

    ax.plot(eq["date"], eq["equity"], label="Equity", linewidth=1.5)
    ax.plot(eq["date"], eq["cash"], label="Cash", linewidth=0.8, alpha=0.6)
    ax.fill_between(
        eq["date"], eq["cash"], eq["equity"], alpha=0.15, label="Position Value"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Value")
    ax.set_title("Equity Curve")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_drawdown(eq: pd.DataFrame) -> plt.Figure:
    """Plot drawdown from peak.

    Parameters
    ----------
    eq : DataFrame
        Equity curve with columns: date, equity.

    Returns
    -------
    Figure
        Matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(10, 3))
    if eq.empty:
        ax.set_title("Drawdown (no data)")
        return fig

    equity = eq["equity"].values
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / np.where(peak > 0, peak, 1)

    ax.fill_between(eq["date"], drawdown, 0, color="red", alpha=0.3)
    ax.plot(eq["date"], drawdown, color="red", linewidth=0.8)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.set_title("Drawdown from Peak")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_backtest_summary(result: dict) -> plt.Figure:
    """Plot backtest summary: equity curve + drawdown + metrics text.

    Parameters
    ----------
    result : dict
        Backtest result with keys: equity_curve, metrics.

    Returns
    -------
    Figure
        Matplotlib Figure with subplots.
    """
    eq = result["equity_curve"]
    metrics = result.get("metrics", {})

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), height_ratios=[3, 1])

    # Equity curve
    if not eq.empty:
        ax1.plot(eq["date"], eq["equity"], label="Equity", linewidth=1.5)
        ax1.fill_between(eq["date"], eq["equity"], eq["equity"].iloc[0], alpha=0.1)
    ax1.set_ylabel("Equity")
    ax1.set_title("Backtest Summary")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Drawdown
    if not eq.empty:
        equity = eq["equity"].values
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / np.where(peak > 0, peak, 1)
        ax2.fill_between(eq["date"], drawdown, 0, color="red", alpha=0.3)
        ax2.plot(eq["date"], drawdown, color="red", linewidth=0.8)
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.3)

    # Metrics text
    if metrics:
        text = (
            f"Return: {metrics.get('total_return', 0):.2%}  |  "
            f"Annual: {metrics.get('annual_return', 0):.2%}  |  "
            f"Sharpe: {metrics.get('sharpe_ratio', 0):.2f}  |  "
            f"MaxDD: {metrics.get('max_drawdown', 0):.2%}  |  "
            f"Win: {metrics.get('win_rate', 0):.0%}  |  "
            f"Trades: {metrics.get('trade_count', 0)}"
        )
        fig.suptitle(text, fontsize=9, y=0.98)

    fig.tight_layout()
    return fig
