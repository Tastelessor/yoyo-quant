"""Pipeline test: signals -> portfolio -> risk -> backtest -> visualization."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.visualization.charts import plot_backtest_summary


def _make_prices():
    """5 days of prices for 2 stocks."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04",
         "2024-01-05", "2024-01-08"]
    )
    return pd.DataFrame({
        "date": dates.tolist() * 2,
        "code": ["000001"] * 5 + ["600519"] * 5,
        "close": [
            10.0, 10.5, 11.0, 10.8, 11.2,
            1800.0, 1810.0, 1790.0, 1820.0, 1850.0,
        ],
    })


def _make_signals():
    """Buy signals on day 1."""
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
        "code": ["000001", "600519"],
        "signal": [1, 1],
        "confidence": [0.8, 0.9],
    })


def test_full_pipeline_produces_valid_output():
    """signals -> equal_weight -> apply_position_limit -> engine -> chart."""
    signals = _make_signals()
    prices = _make_prices()

    # Portfolio allocation
    positions = equal_weight(signals, prices, capital=100_000)
    assert not positions.empty
    assert set(positions.columns) == {"date", "code", "weight", "shares"}

    # Risk: cap at 60% (both are 50%, so no change)
    adjusted = apply_position_limit(positions, max_weight=0.6)
    assert set(adjusted.columns) == {"date", "code", "weight", "shares"}

    # Backtest
    engine = BacktestEngine(capital=100_000)
    result = engine.run(adjusted, prices)
    assert "trades" in result
    assert "equity_curve" in result
    assert "metrics" in result

    # Visualization
    fig = plot_backtest_summary(result)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_pipeline_with_position_limit():
    """Position limit forces redistribution before backtest."""
    signals = _make_signals()
    prices = _make_prices()

    positions = equal_weight(signals, prices, capital=100_000)
    # Cap at 30% — both are 50%, so both get capped
    adjusted = apply_position_limit(positions, max_weight=0.3)
    weights = adjusted["weight"].values
    assert all(w <= 0.3 + 1e-8 for w in weights)

    engine = BacktestEngine(capital=100_000)
    result = engine.run(adjusted, prices)
    # Should still produce valid output
    assert len(result["equity_curve"]) > 0
    assert result["metrics"]["trade_count"] >= 0


def test_pipeline_schema_continuity():
    """Each module's output schema is consumed correctly by the next."""
    signals = _make_signals()
    prices = _make_prices()

    # Step 1: portfolio output has date, code, weight, shares
    positions = equal_weight(signals, prices, capital=100_000)
    assert "weight" in positions.columns
    assert "shares" in positions.columns

    # Step 2: risk output preserves same schema
    adjusted = apply_position_limit(positions, max_weight=0.5)
    assert "weight" in adjusted.columns
    assert "shares" in adjusted.columns

    # Step 3: engine consumes positions and produces trades + equity
    engine = BacktestEngine(capital=100_000)
    result = engine.run(adjusted, prices)
    assert "date" in result["trades"].columns
    assert "equity" in result["equity_curve"].columns
    assert "total_return" in result["metrics"]
