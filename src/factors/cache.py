"""因子结果磁盘缓存（parquet）。

缓存键 = (因子名, 参数哈希, 数据指纹)：
- 参数哈希：params dict 的稳定序列化哈希，调参不串缓存
- 数据指纹：输入数据内容的轻量哈希，数据范围/内容变化即失效

路径：``{cache_dir}/{factor_name}/{param_hash}_{fingerprint}.parquet``
原子写（tmp + rename），避免并发写坏文件。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_CACHE_DIR = Path("data/factors")

_ALIGN_COLS = ["date", "code", "value"]


def get_default_cache_dir() -> Path:
    """默认缓存目录：优先环境变量 ``FACTOR_CACHE_DIR``。"""
    env = os.environ.get("FACTOR_CACHE_DIR")
    return Path(env) if env else DEFAULT_CACHE_DIR


def params_hash(params: dict) -> str:
    """参数 dict 的稳定哈希（16 hex）。空参数用固定串，避免路径噪音。"""
    if not params:
        return "default"
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def fingerprint(df: pd.DataFrame) -> str:
    """输入数据内容指纹（16 hex）：基于排序后的非 date/code 列哈希。

    只依赖数据内容，不依赖行顺序（先按 code, date 排序再哈希），
    保证同一批数据的不同排列命中同一缓存。
    """
    cols = [c for c in df.columns if c not in ("date", "code")]
    if not cols:
        cols = list(df.columns)
    vals = df.sort_values(["code", "date"])[cols].reset_index(drop=True)
    h = pd.util.hash_pandas_object(vals, index=False)
    return hashlib.sha256(h.values.tobytes()).hexdigest()[:16]


def _cache_path(cache_dir: str | Path, name: str, params: dict, fp: str) -> Path:
    return Path(cache_dir) / name / f"{params_hash(params)}_{fp}.parquet"


def load_cached(
    name: str, df: pd.DataFrame, params: dict, cache_dir: str | Path
) -> pd.Series | None:
    """命中返回与 df（已按 code, date 排序）等长的 Series，未命中返回 None。

    (date, code) 序列与输入不一致、长度不一致或文件损坏时视为未命中。
    """
    path = _cache_path(cache_dir, name, params, fingerprint(df))
    if not path.is_file():
        return None
    try:
        cached = pd.read_parquet(path)
    except Exception:
        return None
    if set(cached.columns) != set(_ALIGN_COLS):
        return None
    if len(cached) != len(df):
        return None
    align = df[["date", "code"]].reset_index(drop=True)
    if not (
        (cached["date"].values == align["date"].values).all()
        and (cached["code"].values == align["code"].values).all()
    ):
        return None
    return cached["value"].reset_index(drop=True)


def save_cached(
    name: str,
    df: pd.DataFrame,
    params: dict,
    series: pd.Series,
    cache_dir: str | Path,
) -> None:
    """保存 series（与 df 排序后等长）到缓存，原子写。"""
    path = _cache_path(cache_dir, name, params, fingerprint(df))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pd.DataFrame(
        {
            "date": df["date"].values,
            "code": df["code"].values,
            "value": np.asarray(series, dtype=np.float64),
        }
    )
    tmp = path.with_name(path.name + ".tmp")
    payload.to_parquet(tmp, index=False)
    tmp.replace(path)


def clear_factor_cache(
    name: str | None = None, cache_dir: str | Path | None = None
) -> int:
    """删除缓存文件（可只删某因子），返回删除的文件数。"""
    root = Path(cache_dir) if cache_dir else get_default_cache_dir()
    if not root.exists():
        return 0
    target = root / name if name else root
    removed = 0
    for p in target.rglob("*.parquet"):
        p.unlink()
        removed += 1
    return removed
