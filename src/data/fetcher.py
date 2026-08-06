import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_PROXY_URL = "https://quantdata888.duckdns.org"

# fetch_fundamentals 必需返回列（total_mv/circ_mv 亿元、turnover_rate %）
FUNDAMENTALS_COLUMNS = [
    "code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"
]


def _to_ts_code(code: str) -> str:
    """将纯数字代码转换为 tushare 格式 (000001 -> 000001.SZ)。"""
    if code.startswith("6"):
        return f"{code}.SH"
    return f"{code}.SZ"


def fetch_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """获取 A 股日线行情 (tushare)。

    Parameters
    ----------
    code : str
        股票代码，如 "000001"。
    start : str
        开始日期，格式 "YYYY-MM-DD"。
    end : str
        结束日期，格式 "YYYY-MM-DD"。

    Returns
    -------
    DataFrame
        符合 OHLCV schema 的日线数据。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_code = _to_ts_code(code)

    # Retry with backoff on rate limit / transient proxy failures
    raw = None
    retryable = (
        "过快",
        "频率",
        "每分钟",
        "最多访问",
        "访问次数",
        "unavailable",
        "timeout",
        "timed out",
    )
    for attempt in range(3):
        try:
            raw = api.daily(
                ts_code=ts_code,
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
            )
            break
        except Exception as e:
            if any(k in str(e) for k in retryable):
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Temporary failure on %s (%s), retrying in %ds...",
                    code,
                    e,
                    wait,
                )
                time.sleep(wait)
            else:
                raise

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "code",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
            ]
        )

    df = raw.rename(columns={"trade_date": "date", "vol": "volume"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "code", "open", "high", "low", "close", "pre_close", "volume"]]


def fetch_index_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """获取指数日线行情 (tushare index_daily)。

    Parameters
    ----------
    code : str
        指数代码，如 "000300"（沪深300）。
    start : str
        开始日期，格式 "YYYY-MM-DD"。
    end : str
        结束日期，格式 "YYYY-MM-DD"。

    Returns
    -------
    DataFrame
        包含 date, code, open, high, low, close, volume 列。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_code = _to_ts_code(code)
    raw = api.index_daily(
        ts_code=ts_code,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "code",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
            ]
        )

    df = raw.rename(columns={"trade_date": "date", "vol": "volume"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "code", "open", "high", "low", "close", "pre_close", "volume"]]


def fetch_index_constituents(
    index_code: str,
    date: str | None = None,
    cache_dir: Path | str | None = None,
) -> list[str]:
    """获取指数成分股代码列表 (tushare index_weight)。

    Parameters
    ----------
    index_code : str
        指数代码，如 "000905.SH"（中证500）。
    date : str | None
        快照日期，格式 "YYYY-MM-DD"。None 时不传日期过滤。
    cache_dir : Path | str | None
        缓存目录。None 时使用 data/raw/index/。

    Returns
    -------
    list[str]
        去重后的 6 位股票代码列表。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "index"
    else:
        cache_dir = Path(cache_dir)

    date_tag = date or "latest"
    cache_file = cache_dir / f"{index_code}_{date_tag}.parquet"

    if cache_file.exists():
        cached = pd.read_parquet(cache_file)
        return list(cached["code"])

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    raw = api.index_weight(index_code=index_code)

    if raw is None or raw.empty:
        return []

    # Filter to specific date if requested, otherwise use latest
    if date is not None:
        date_str = date.replace("-", "")
        filtered = raw[raw["trade_date"] == date_str]
        if not filtered.empty:
            raw = filtered
        # else: date not found, fall back to latest snapshot
        else:
            latest_date = raw["trade_date"].max()
            raw = raw[raw["trade_date"] == latest_date]
    else:
        latest_date = raw["trade_date"].max()
        raw = raw[raw["trade_date"] == latest_date]

    if raw.empty:
        return []

    codes = raw["con_code"].str.split(".").str[0].unique().tolist()

    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"code": sorted(codes)}).to_parquet(cache_file, index=False)

    return sorted(codes)


def fetch_daily_batch(
    codes: list[str],
    start: str,
    end: str,
    raw_dir: Path | str,
    sleep_sec: float = 0.5,
    progress: bool = True,
    workers: int = 1,
) -> pd.DataFrame:
    """批量获取日线行情，带缓存和限速（支持并发）。

    对每只股票先检查 parquet 缓存，未命中时调用 fetch_daily 并保存。
    未缓存的 API 调用后 sleep 以尊重频率限制。

    workers=1（默认）为串行：保持旧行为，未缓存调用之间 sleep；
    workers>1 时用线程池并发，每个 worker 在每次 API 调用后 sleep。
    任一只股票失败会抛出异常，已保存的缓存保留（断点可续）。

    Parameters
    ----------
    codes : list[str]
        股票代码列表。
    start, end : str
        日期范围，格式 "YYYY-MM-DD"。
    raw_dir : Path | str
        parquet 缓存目录。
    sleep_sec : float
        未缓存 API 调用后的 sleep 秒数（串行：调用间；并发：每 worker 调用后）。
    progress : bool
        是否每 50 只打印进度。
    workers : int
        并发线程数。默认 1（串行）。

    Returns
    -------
    DataFrame
        所有股票拼接后的 OHLCV 数据。
    """
    from data.storage import save_parquet

    raw_dir = Path(raw_dir)

    def _fetch_one(code: str) -> pd.DataFrame:
        cache_path = raw_dir / f"{code}.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)
        df = fetch_daily(code, start, end)
        save_parquet(df, cache_path)
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        return df

    def _log_progress(done: int) -> None:
        logger.info("Loaded %d / %d stocks", done, len(codes))

    frames: list[pd.DataFrame] = []

    if workers <= 1:
        fetched = 0
        for i, code in enumerate(codes):
            cache_path = raw_dir / f"{code}.parquet"
            if cache_path.exists():
                frames.append(pd.read_parquet(cache_path))
            else:
                df = fetch_daily(code, start, end)
                save_parquet(df, cache_path)
                fetched += 1
                if fetched > 1 and sleep_sec > 0:
                    time.sleep(sleep_sec)
                frames.append(df)
            if progress and (i + 1) % 50 == 0:
                _log_progress(i + 1)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_fetch_one, code) for code in codes]
            for i, future in enumerate(as_completed(futures), 1):
                frames.append(future.result())
                if progress and i % 50 == 0:
                    _log_progress(i)

    if not frames:
        return pd.DataFrame(
            columns=[
                "date",
                "code",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
            ]
        )

    return pd.concat(frames, ignore_index=True)


def fetch_all_stocks(
    date: str | None = None,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """获取所有上市 A 股基本信息 (tushare stock_basic)。

    Parameters
    ----------
    date : str | None
        快照日期，格式 "YYYY-MM-DD"。用于缓存键。
    cache_dir : Path | str | None
        缓存目录。None 时使用 data/raw/index/。

    Returns
    -------
    DataFrame
        Columns: code, name, industry, market, list_date.
        已排除 ST 和北交所。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "index"
    else:
        cache_dir = Path(cache_dir)

    date_tag = date or "latest"
    cache_file = cache_dir / f"all_stocks_{date_tag}.parquet"

    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    raw = api.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,name,industry,market,list_date",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["code", "name", "industry", "market", "list_date"])

    df = raw.rename(columns={"ts_code": "code"})
    # Strip exchange suffix: 000001.SZ -> 000001
    df["code"] = df["code"].str.split(".").str[0]

    # Exclude ST stocks
    mask_st = df["name"].str.contains("ST", case=False, na=False)
    # Exclude 北交所：market 字段优先（覆盖 43/83/87/92 等全部北交所代码段），
    # 前缀 (4, 8, 920) 兜底兼容 market 列缺失的旧缓存
    mask_bj = df["code"].str.startswith(("4", "8", "920"))
    if "market" in df.columns:
        mask_bj = mask_bj | df["market"].eq("北交所")
    df = df[~mask_st & ~mask_bj].reset_index(drop=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_file, index=False)

    return df


def fetch_fundamentals(
    date: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """获取全市场基本面数据 (tushare daily_basic)。

    Parameters
    ----------
    date : str
        交易日期，格式 "YYYY-MM-DD"。
    cache_dir : Path | str | None
        缓存目录。None 时使用 data/raw/fundamentals/。

    Returns
    -------
    DataFrame
        Columns: code, pe, pb, total_mv (亿元), circ_mv (亿元), turnover_rate (%)。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = (
            Path(__file__).resolve().parents[2] / "data" / "raw" / "fundamentals"
        )
    else:
        cache_dir = Path(cache_dir)

    date_str = date.replace("-", "")
    cache_file = cache_dir / f"{date_str}.parquet"

    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        # 旧缓存（如本 task 前落盘的 4 列版本）缺必需列时忽略并走 API 重拉，自动迁移
        if all(col in df.columns for col in FUNDAMENTALS_COLUMNS):
            return df

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    raw = api.daily_basic(
        trade_date=date_str,
        fields="ts_code,trade_date,pe,pb,total_mv,circ_mv,turnover_rate",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(columns=FUNDAMENTALS_COLUMNS)

    df = raw.rename(columns={"ts_code": "code"})
    df["code"] = df["code"].str.split(".").str[0]
    # total_mv / circ_mv 单位万元 → 亿元；turnover_rate 原样（%）
    df["total_mv"] = df["total_mv"] / 10_000
    df["circ_mv"] = df["circ_mv"] / 10_000

    cache_dir.mkdir(parents=True, exist_ok=True)
    df[FUNDAMENTALS_COLUMNS].to_parquet(cache_file, index=False)

    return df[FUNDAMENTALS_COLUMNS]
