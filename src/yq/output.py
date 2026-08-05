"""yq CLI 输出渲染层：DataFrame/Series/dict → 文本表格或 JSON。

所有命令统一约定：
- 默认输出终端可读的文本表格
- ``--json`` 输出合法 JSON（NaN/NaT/inf → null），供脚本与 notebook 消费
"""

import json
from typing import Any

import numpy as np
import pandas as pd


def _clean(value: Any) -> Any:
    """把 numpy/pandas 标量转成 JSON 可序列化的 Python 值（NaN → None）。"""
    if value is None:
        return None
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def render_dataframe(df: pd.DataFrame, *, as_json: bool) -> str:
    """DataFrame → 文本表格（to_string）或 JSON records。"""
    if as_json:
        return json.dumps(_records(df), ensure_ascii=False, indent=2)
    return df.to_string(index=False)


def render_series(series: pd.Series, *, as_json: bool) -> str:
    """Series → (key, value) 两列，保留 Series name 之外的索引值。"""
    frame = pd.DataFrame({"key": series.index, "value": series.values})
    return render_dataframe(frame, as_json=as_json)


def render_dict(data: dict, *, as_json: bool) -> str:
    """标量 dict → JSON 对象或 ``key: value`` 行。"""
    if as_json:
        return json.dumps(
            {k: _clean(v) for k, v in data.items()}, ensure_ascii=False, indent=2
        )
    return "\n".join(f"{k}: {v}" for k, v in data.items())
