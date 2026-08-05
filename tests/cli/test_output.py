"""yq CLI 输出渲染层测试。"""

import json

import numpy as np
import pandas as pd

from yq.output import render_dataframe, render_dict, render_series


def test_render_dataframe_text():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    text = render_dataframe(df, as_json=False)
    assert "a" in text and "b" in text
    assert "1" in text and "x" in text


def test_render_dataframe_json_records():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out = json.loads(render_dataframe(df, as_json=True))
    assert out == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


def test_render_dataframe_json_nan_becomes_null():
    """JSON 必须合法：NaN/NaT → null（json.dumps 默认 allow_nan 输出非法 JSON）。"""
    df = pd.DataFrame({"a": [1.0, np.nan], "d": [pd.Timestamp("2024-01-01"), pd.NaT]})
    out = json.loads(render_dataframe(df, as_json=True))
    assert out[0]["a"] == 1.0
    assert out[1]["a"] is None
    assert out[1]["d"] is None


def test_render_dataframe_json_datetime_iso():
    df = pd.DataFrame({"d": [pd.Timestamp("2024-01-01")]})
    out = json.loads(render_dataframe(df, as_json=True))
    assert out[0]["d"] == "2024-01-01T00:00:00"


def test_render_series_pairs_with_keys():
    """Series 渲染成 (key, value) 行，NaN → None。"""
    s = pd.Series([1.5, np.nan], index=["a", "b"], name="f")
    out = json.loads(render_series(s, as_json=True))
    assert out == [{"key": "a", "value": 1.5}, {"key": "b", "value": None}]


def test_render_series_text_contains_values():
    s = pd.Series([1.5, 2.5], index=["a", "b"], name="f")
    text = render_series(s, as_json=False)
    assert "1.5" in text and "2.5" in text


def test_render_dict_json_and_text():
    out = json.loads(render_dict({"n": 3, "ok": True}, as_json=True))
    assert out == {"n": 3, "ok": True}
    text = render_dict({"n": 3}, as_json=False)
    assert "n" in text and "3" in text


def test_render_empty_dataframe_json():
    df = pd.DataFrame(columns=["a", "b"])
    assert json.loads(render_dataframe(df, as_json=True)) == []
    text = render_dataframe(df, as_json=False)
    assert "a" in text
