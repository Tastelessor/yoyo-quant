"""Drawdown attribution analysis.

Identifies worst drawdown periods and analyzes their sources:
- Individual stock PnL contribution
- Industry concentration during drawdowns
- Timing patterns
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.engine import BacktestEngine
from src.config.loader import load_config
from src.data import validate_ohlcv
from src.data.fetcher import fetch_all_stocks, fetch_daily_batch
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable
from src.strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def find_drawdowns(equity_curve: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """Find the worst drawdown periods in the equity curve."""
    eq = equity_curve.copy()
    eq["peak"] = eq["equity"].cummax()
    eq["drawdown"] = (eq["equity"] - eq["peak"]) / eq["peak"]

    # Find drawdown periods (peak to trough to recovery)
    drawdowns = []
    in_drawdown = False
    dd_start = None
    dd_trough = None
    dd_trough_val = 0.0

    for _, row in eq.iterrows():
        if row["drawdown"] < 0:
            if not in_drawdown:
                dd_start = row["date"]
                dd_trough = row["date"]
                dd_trough_val = row["drawdown"]
                in_drawdown = True
            elif row["drawdown"] < dd_trough_val:
                dd_trough = row["date"]
                dd_trough_val = row["drawdown"]
        else:
            if in_drawdown:
                drawdowns.append({
                    "start": dd_start,
                    "trough": dd_trough,
                    "end": row["date"],
                    "max_dd": dd_trough_val,
                    "duration_days": (row["date"] - dd_start).days,
                })
                in_drawdown = False

    # Sort by severity
    drawdowns.sort(key=lambda x: x["max_dd"])
    return drawdowns[:top_n]


def attribute_drawdown(
    trades: pd.DataFrame,
    industry_map: dict[str, str],
    dd_start: pd.Timestamp,
    dd_end: pd.Timestamp,
) -> dict:
    """Analyze PnL contribution during a drawdown period."""
    mask = (trades["date"] >= dd_start) & (trades["date"] <= dd_end)
    period_trades = trades[mask].copy()

    if period_trades.empty:
        return {"total_pnl": 0.0, "by_stock": {}, "by_industry": {}}

    # PnL by stock
    stock_pnl = period_trades.groupby("code")["pnl"].sum().sort_values()

    # PnL by industry
    period_trades["industry"] = period_trades["code"].map(
        lambda c: industry_map.get(c, "其他")
    )
    industry_pnl = period_trades.groupby("industry")["pnl"].sum().sort_values()

    return {
        "total_pnl": period_trades["pnl"].sum(),
        "n_trades": len(period_trades),
        "by_stock": stock_pnl.to_dict(),
        "by_industry": industry_pnl.to_dict(),
        "worst_stocks": stock_pnl.head(5).to_dict(),
        "best_stocks": stock_pnl.tail(5).to_dict(),
        "worst_industries": industry_pnl.head(5).to_dict(),
    }


# ── Load data ────────────────────────────────────────────────────────────
print("=" * 70)
print("Drawdown Attribution Analysis")
print("=" * 70)

cfg = load_config(PROJECT_ROOT / "configs" / "experiment_stock_selector.yaml")
codes = resolve_universe(cfg["universe"])
start = cfg["universe"]["start_date"]
end = cfg["universe"]["end_date"]

print(f"\nLoading {len(codes)} stocks ({start} ~ {end})...", flush=True)
data = fetch_daily_batch(codes, start, end, RAW_DIR, sleep_sec=0, progress=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days")

# Industry mapping
all_stocks = fetch_all_stocks(date=cfg["universe"]["fetch_date"])
industry_map = dict(zip(all_stocks["code"], all_stocks["industry"]))

# ── Run backtest ─────────────────────────────────────────────────────────
print("\nRunning backtest (gtja_momentum)...", flush=True)
strategy = get_strategy("gtja_momentum", rebalance=10, top_n=5, bottom_n=3)
signals = strategy.generate_signal(data)
signals = filter_tradable(data, signals)
signals = enforce_t1(signals)
prices = data[["date", "code", "close"]].drop_duplicates()
positions = equal_weight(signals, prices, capital=1_000_000)
positions = apply_position_limit(positions, max_weight=0.3)

engine = BacktestEngine(capital=1_000_000)
result = engine.run(positions, prices)
trades = result["trades"]
eq = result["equity_curve"]
m = result["metrics"]

print(f"  Total return: {m['total_return']*100:.1f}%")
print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
print(f"  MaxDD: {m['max_drawdown']*100:.1f}%")
print(f"  Trades: {len(trades)}")

# ── Find worst drawdowns ────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Top 5 Worst Drawdowns")
print(f"{'─' * 70}")

drawdowns = find_drawdowns(eq, top_n=5)
for i, dd in enumerate(drawdowns, 1):
    print(f"\n  #{i}: {dd['max_dd']*100:.1f}% "
          f"({dd['start'].strftime('%Y-%m-%d')} → "
          f"{dd['trough'].strftime('%Y-%m-%d')} → "
          f"{dd['end'].strftime('%Y-%m-%d')}, "
          f"{dd['duration_days']} days)")

    # Attribute this drawdown
    attr = attribute_drawdown(trades, industry_map, dd["start"], dd["end"])
    print(f"     Total PnL: {attr['total_pnl']:,.0f}")
    print(f"     Trades: {attr['n_trades']}")

    if attr["worst_stocks"]:
        print("     Worst stocks:")
        for code, pnl in list(attr["worst_stocks"].items())[:3]:
            ind = industry_map.get(code, "?")
            print(f"       {code} ({ind}): {pnl:,.0f}")

    if attr["worst_industries"]:
        print("     Worst industries:")
        for ind, pnl in list(attr["worst_industries"].items())[:3]:
            print(f"       {ind}: {pnl:,.0f}")

# ── Overall PnL by industry ─────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Overall PnL by Industry (Top 10 losers)")
print(f"{'─' * 70}")

trades_with_ind = trades.copy()
trades_with_ind["industry"] = trades_with_ind["code"].map(
    lambda c: industry_map.get(c, "其他")
)
industry_total_pnl = trades_with_ind.groupby("industry")["pnl"].sum().sort_values()
for ind, pnl in industry_total_pnl.head(10).items():
    print(f"  {ind:<12} {pnl:>12,.0f}")

print(f"\n{'─' * 70}")
print("Overall PnL by Industry (Top 5 winners)")
print(f"{'─' * 70}")
for ind, pnl in industry_total_pnl.tail(5).items():
    print(f"  {ind:<12} {pnl:>12,.0f}")

# ── PnL by stock (concentration) ────────────────────────────────────────
print(f"\n{'─' * 70}")
print("PnL Concentration: Top 10 stocks by |PnL|")
print(f"{'─' * 70}")

stock_total_pnl = trades.groupby("code")["pnl"].sum()
top_abs = stock_total_pnl.abs().sort_values(ascending=False).head(10)
for code in top_abs.index:
    pnl = stock_total_pnl[code]
    ind = industry_map.get(code, "?")
    print(f"  {code} ({ind:<8}) {pnl:>12,.0f}")

# ── Win rate and avg PnL ────────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("Trade Statistics")
print(f"{'─' * 70}")

sell_trades = trades[trades["action"] == "sell"]
if not sell_trades.empty:
    wins = sell_trades[sell_trades["pnl"] > 0]
    losses = sell_trades[sell_trades["pnl"] < 0]
    print(f"  Sell trades: {len(sell_trades)}")
    print(f"  Win rate: {len(wins)/len(sell_trades)*100:.1f}%")
    print(f"  Avg win: {wins['pnl'].mean():,.0f}" if len(wins) > 0 else "  Avg win: N/A")
    print(f"  Avg loss: {losses['pnl'].mean():,.0f}" if len(losses) > 0 else "  Avg loss: N/A")
    print(f"  Max single loss: {sell_trades['pnl'].min():,.0f}")
    print(f"  Max single win: {sell_trades['pnl'].max():,.0f}")
    # Profit factor
    total_wins = wins["pnl"].sum() if len(wins) > 0 else 0
    total_losses = abs(losses["pnl"].sum()) if len(losses) > 0 else 0
    if total_losses > 0:
        print(f"  Profit factor: {total_wins/total_losses:.2f}")

print(f"\n{'=' * 70}")
print("Done.")
