"""yq factor monitor 子命令测试：参数解析、状态表、变更 diff。

覆盖：
- 缺 --data 报错（typer 必填校验）
- 小数据端到端：文本状态表 + --json 结构（status/changes/config）
- 纯函数：build_status_table（每键一行、最新值、最近切换日期、dead 置顶排序）
          render_changes（人类可读文本）
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from yq.cli import app
from yq.monitor import build_status_table, render_changes

runner = CliRunner()


def _price_df(n_stocks: int = 5, n_days: int = 20, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    rows = []
    for i in range(n_stocks):
        code = f"S{i:02d}"
        close = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n_days))
        volume = rng.integers(100_000, 1_000_000, n_days)
        for d, c, v in zip(dates, close, volume):
            rows.append((d, code, float(c), int(v)))
    df = pd.DataFrame(rows, columns=["date", "code", "close", "volume"])
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def _write_price(tmp_path: pytest.TempPathFactory, **kw) -> str:
    path = tmp_path / "price.parquet"
    _price_df(**kw).to_parquet(path, index=False)
    return str(path)


# ---------------- 参数解析 ----------------


def test_monitor_missing_data_errors():
    """缺 --data 时 typer 必填校验报错。"""
    result = runner.invoke(app, ["factor", "monitor"])
    assert result.exit_code != 0
    assert "--data" in result.stderr


# ---------------- 端到端（小数据） ----------------


def test_monitor_text_status_table(tmp_path, monkeypatch):
    """小数据跑通：文本输出包含状态表列头与因子名。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
    price = _write_price(tmp_path, n_stocks=20, n_days=150, seed=7)
    out_dir = tmp_path / "audit"
    result = runner.invoke(
        app,
        [
            "factor",
            "monitor",
            "--data",
            price,
            "--factor",
            "calc_hv",
            "--windows",
            "5",
            "--window",
            "60",
            "--output-dir",
            str(out_dir),
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "factor" in result.stdout
    assert "state" in result.stdout
    assert "calc_hv" in result.stdout
    # 落盘 state.parquet
    assert (out_dir / "state.parquet").exists()


def test_monitor_json_structure(tmp_path, monkeypatch):
    """--json 输出 status/changes/config 三块，status 行含关键字段。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
    price = _write_price(tmp_path, n_stocks=20, n_days=150, seed=7)
    result = runner.invoke(
        app,
        [
            "factor",
            "monitor",
            "--data",
            price,
            "--factor",
            "calc_hv",
            "--windows",
            "5,20",
            "--window",
            "60",
            "--output-dir",
            str(tmp_path / "audit"),
            "--no-cache",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert {"status", "changes", "config"} <= set(payload)
    assert payload["config"]["windows"] == [5, 20]
    assert payload["config"]["window"] == 60
    status = payload["status"]
    assert isinstance(status, list) and len(status) == 2  # calc_hv × 2 个 forward 窗口
    assert {
        "factor",
        "fwd_window",
        "state",
        "t_stat",
        "rolling_ir",
        "sustain_days",
    } <= set(status[0])


# ---------------- build_status_table 纯函数 ----------------


def _state_long_table() -> pd.DataFrame:
    """构造 (factor × fwd_window) 各 2 键、多日期、含切换的 state 长表。"""
    dates = pd.bdate_range("2024-01-01", periods=100)
    rows = []
    # factor A / fwd 5：前 50 天 active，后 50 天 dead（2024-03-11 附近切换）
    for i, d in enumerate(dates):
        state = "active" if i < 50 else "dead"
        rows.append(
            {
                "date": d,
                "factor": "fa",
                "fwd_window": 5,
                "ic": 0.1,
                "rolling_ic": 0.1,
                "rolling_ir": 0.8 if state == "active" else 0.1,
                "t_stat": 2.5 if state == "active" else 0.5,
                "state": state,
                "sustain_days": 25 if state == "active" else 30,
            }
        )
    # factor A / fwd 20：全程 decaying（无切换）
    for d in dates:
        rows.append(
            {
                "date": d,
                "factor": "fa",
                "fwd_window": 20,
                "ic": 0.05,
                "rolling_ic": 0.05,
                "rolling_ir": 0.4,
                "t_stat": 1.5,
                "state": "decaying",
                "sustain_days": 40,
            }
        )
    # factor B / fwd 5：全程 active（无切换）
    for d in dates:
        rows.append(
            {
                "date": d,
                "factor": "fb",
                "fwd_window": 5,
                "ic": 0.12,
                "rolling_ic": 0.12,
                "rolling_ir": 1.0,
                "t_stat": 3.0,
                "state": "active",
                "sustain_days": 60,
            }
        )
    return pd.DataFrame(rows)


def test_build_status_table_latest_row_per_key():
    """每个 (factor, fwd_window) 只取最新日期一行，值为最新。"""
    table = build_status_table(_state_long_table())
    assert list(table["factor"]) == ["fa", "fa", "fb"]
    assert list(table["fwd_window"]) == [5, 20, 5]
    fa5 = table[(table["factor"] == "fa") & (table["fwd_window"] == 5)].iloc[0]
    assert fa5["state"] == "dead"
    assert fa5["t_stat"] == 0.5
    assert fa5["sustain_days"] == 30


def test_build_status_table_last_switch_date():
    """最近切换日期：fa/fwd5 最后一次 active→dead 切换 = 第 50 天；无切换的键为 NaT。"""
    table = build_status_table(_state_long_table())
    fa5 = table[(table["factor"] == "fa") & (table["fwd_window"] == 5)].iloc[0]
    assert fa5["last_switch_date"] == pd.Timestamp("2024-03-11")
    fa20 = table[(table["factor"] == "fa") & (table["fwd_window"] == 20)].iloc[0]
    assert pd.isna(fa20["last_switch_date"])
    fb5 = table[(table["factor"] == "fb") & (table["fwd_window"] == 5)].iloc[0]
    assert pd.isna(fb5["last_switch_date"])


def test_build_status_table_dead_first():
    """状态排序：dead 置顶，其次 reverse/decaying/active。"""
    table = build_status_table(_state_long_table())
    assert table.iloc[0]["state"] == "dead"
    assert list(table["state"]) == ["dead", "decaying", "active"]


# ---------------- render_changes 纯函数 ----------------


def test_render_changes_text():
    changes = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-03-11"),
                "factor": "fa",
                "fwd_window": 5,
                "old_state": "active",
                "new_state": "dead",
            },
            {
                "date": pd.Timestamp("2024-04-01"),
                "factor": "fb",
                "fwd_window": 5,
                "old_state": "dead",
                "new_state": "active",
            },
        ]
    )
    text = render_changes(changes)
    assert "状态切换" in text
    assert "fa" in text and "active → dead" in text
    assert "fb" in text and "dead → active" in text


def test_render_changes_empty():
    cols = ["date", "factor", "fwd_window", "old_state", "new_state"]
    text = render_changes(pd.DataFrame(columns=cols))
    assert "无状态切换" in text


def test_monitor_saves_figures(tmp_path, monkeypatch):
    """monitor 输出 figures 键：health_heatmap + 每 (factor, fwd) 一张 lifecycle 图。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
    price = _write_price(tmp_path, n_stocks=20, n_days=150, seed=7)
    out_dir = tmp_path / "audit"
    result = runner.invoke(
        app,
        [
            "factor",
            "monitor",
            "--data",
            price,
            "--factor",
            "calc_hv",
            "--windows",
            "5,20",
            "--window",
            "60",
            "--output-dir",
            str(out_dir),
            "--no-cache",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "figures" in payload
    assert len(payload["figures"]) == 3  # heatmap + calc_hv×fwd5 + calc_hv×fwd20
    for p in payload["figures"]:
        assert Path(p).exists()


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """跑测试期间把因子缓存目录隔离到 tmp_path，避免污染真实 data/factors。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
