"""全市场近 3 年日 K 拉取 + 清洗。

用法：``.venv/bin/python notebooks/fetch_full_market.py``

输出：
- ``data/raw/full_market_3y/{code}.parquet``   原始 OHLCV（含 pre_close，按股票缓存）
- ``data/clean/full_market_ohlcv.parquet``     清洗后（含 limit_up / limit_down /
  is_suspended，停牌日补齐为 is_suspended=True 的行）

股票池来自 ``fetch_all_stocks``（排除 ST / 北交所，最新快照）。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from data.clean import clean_market_data
from data.fetcher import fetch_all_stocks, fetch_daily_batch
from data.storage import save_parquet
from data.trade_calendar import fetch_trade_dates

START = (date.today() - timedelta(days=365 * 3)).isoformat()
END = date.today().isoformat()
RAW_DIR = Path("data/raw/full_market_3y")
CLEAN_PATH = Path("data/clean/full_market_ohlcv.parquet")


def main() -> None:
    all_stocks = fetch_all_stocks(date=END)
    codes = sorted(all_stocks["code"].tolist())
    print(f"[fetch] {len(codes)} stocks, {START} -> {END}")

    raw = fetch_daily_batch(
        codes, START, END, RAW_DIR, sleep_sec=2.0, progress=True, workers=4
    )
    print(f"[fetch] raw rows: {len(raw)}")

    trade_dates = fetch_trade_dates(START, END)
    print(f"[clean] trade days: {len(trade_dates)}")

    clean = clean_market_data(raw, trade_dates=trade_dates)
    save_parquet(clean, CLEAN_PATH)
    print(f"[save] {len(clean)} rows -> {CLEAN_PATH}")
    print(
        "[stats] limit_up=%d limit_down=%d suspended=%d codes=%d range=%s -> %s"
        % (
            int(clean["limit_up"].sum()),
            int(clean["limit_down"].sum()),
            int(clean["is_suspended"].sum()),
            clean["code"].nunique(),
            clean["date"].min().date(),
            clean["date"].max().date(),
        )
    )


if __name__ == "__main__":
    main()
