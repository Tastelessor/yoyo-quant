"""Compute post-neutralization strategy correlation matrix.

Runs each neutralized strategy on the full dataset, extracts daily
returns, and computes pairwise Pearson correlation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import load_config
from data import validate_ohlcv
from data.fetcher import fetch_all_stocks, fetch_daily_batch
from data.filters import detect_limit_price, detect_suspension
from data.universe import resolve_universe
from strategies.registry import get_strategy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def run_strategy_returns(data, strategy_name, industry_map, min_peers=3, **params):
    """Run a strategy and return daily portfolio returns series."""
    strategy = get_strategy(
        strategy_name, industry_map=industry_map, min_peers=min_peers, **params
    )
    signal_df = strategy.generate_signal(data)

    # Compute daily portfolio returns from buy signals
    # For each date, equal-weight buy stocks and compute next-day return
    close_pivot = data.pivot(index="date", columns="code", values="close")
    daily_returns = close_pivot.pct_change()

    buy_signals = signal_df[signal_df["signal"] == 1].copy()
    if buy_signals.empty:
        return pd.Series(dtype=float, name=strategy_name)

    port_returns = []
    for date in sorted(buy_signals["date"].unique()):
        day_buys = buy_signals[buy_signals["date"] == date]["code"].tolist()
        # Use next day's return (we buy at close, earn next day)
        next_dates = sorted(close_pivot.index)
        idx = next_dates.index(date) if date in next_dates else -1
        if idx + 1 < len(next_dates):
            next_date = next_dates[idx + 1]
            if next_date in daily_returns.index:
                rets = daily_returns.loc[next_date, day_buys].dropna()
                if len(rets) > 0:
                    port_returns.append((next_date, rets.mean()))

    if not port_returns:
        return pd.Series(dtype=float, name=strategy_name)

    result = pd.Series(dict(port_returns), name=strategy_name)
    result.index.name = "date"
    return result.sort_index()


# ── Load data ────────────────────────────────────────────────────────────
print("Loading data...", flush=True)
cfg = load_config(PROJECT_ROOT / "configs" / "default.yaml")
codes = resolve_universe(cfg["universe"])
start = cfg["universe"]["start_date"]
end = cfg["universe"]["end_date"]
data = fetch_daily_batch(codes, start, end, RAW_DIR, sleep_sec=0, progress=True)
data = detect_limit_price(data)
data = detect_suspension(data)
validate_ohlcv(data)
print(f"  {data['code'].nunique()} stocks, {data['date'].nunique()} days")

# ── Build industry map ───────────────────────────────────────────────────
all_stocks_df = fetch_all_stocks()
industry_map = dict(zip(all_stocks_df["code"], all_stocks_df["industry"]))

# ── Run strategies ───────────────────────────────────────────────────────
strategies = [
    ("gtja_momentum", {"rebalance": 10, "top_n": 5, "bottom_n": 3}),
    ("reversed_gtja_vwap", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_mean_reversion", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_volume_price", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_trend", {"rebalance": 20, "top_n": 5, "bottom_n": 3}),
    ("gtja_volatility", {"rebalance": 5, "top_n": 3, "bottom_n": 3}),
]

returns_dict = {}
for name, params in strategies:
    print(f"  Running {name}...", end=" ", flush=True)
    ret = run_strategy_returns(data, name, industry_map, **params)
    returns_dict[name] = ret
    print(f"({len(ret)} days)", flush=True)

# ── Build returns DataFrame ──────────────────────────────────────────────
returns_df = pd.DataFrame(returns_dict)
returns_df = returns_df.dropna(how="all")
print(f"\nReturns matrix: {returns_df.shape[0]} days × {returns_df.shape[1]} strategies")

# ── Correlation matrix ───────────────────────────────────────────────────
corr = returns_df.corr()

print(f"\n{'=' * 70}")
print("Post-Neutralization Strategy Correlation Matrix")
print(f"{'=' * 70}\n")

# Pretty print
short_names = {
    "gtja_momentum": "momentum",
    "reversed_gtja_vwap": "rev_vwap",
    "gtja_mean_reversion": "mean_rev",
    "gtja_volume_price": "vol_price",
    "gtja_trend": "trend",
    "gtja_volatility": "volatility",
}

header = f"{'':>12}"
for col in corr.columns:
    header += f" {short_names.get(col, col):>10}"
print(header)
print("-" * len(header))

for idx, row in corr.iterrows():
    line = f"{short_names.get(idx, idx):>12}"
    for col in corr.columns:
        val = row[col]
        line += f" {val:>10.3f}"
    print(line)

# ── Pairwise stats ───────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Pairwise Correlation Summary")
print(f"{'=' * 70}\n")

pairs = []
for i, name_i in enumerate(corr.columns):
    for j, name_j in enumerate(corr.columns):
        if i < j:
            pairs.append((short_names[name_i], short_names[name_j], corr.loc[name_i, name_j]))

pairs.sort(key=lambda x: abs(x[2]), reverse=True)
for n1, n2, r in pairs:
    marker = "***" if abs(r) > 0.5 else "**" if abs(r) > 0.3 else "*" if abs(r) > 0.1 else ""
    print(f"  {n1:>12} × {n2:<12}  {r:+.3f}  {marker}")

# ── Diversification potential ────────────────────────────────────────────
print(f"\n{'=' * 70}")
print("Diversification Potential (top strategy pairs)")
print(f"{'=' * 70}\n")

# For each pair, compute combined Sharpe if correlation is low
for n1, n2, r in pairs[:6]:
    s1 = returns_dict[[k for k, v in short_names.items() if v == n1][0]]
    s2 = returns_dict[[k for k, v in short_names.items() if v == n2][0]]
    # Equal-weight combo
    combo = (s1 + s2) / 2
    combo_sharpe = combo.mean() / combo.std() * np.sqrt(252) if combo.std() > 0 else 0
    s1_sharpe = s1.mean() / s1.std() * np.sqrt(252) if s1.std() > 0 else 0
    s2_sharpe = s2.mean() / s2.std() * np.sqrt(252) if s2.std() > 0 else 0
    print(f"  {n1:>12} × {n2:<12}  corr={r:+.3f}  "
          f"S1={s1_sharpe:.3f}  S2={s2_sharpe:.3f}  combo={combo_sharpe:.3f}")

print(f"\n{'=' * 70}")
print("Done.")
