"""yq cache 子命令测试：info / clear。"""

import json

import pandas as pd
import pytest
from typer.testing import CliRunner

from yq.cli import app

runner = CliRunner()


def _make_cache_files(cache_dir, n_files=3) -> None:
    """构造 factor 缓存目录结构：{factor}/{param_hash}/{start}_{end}.parquet。"""
    root = cache_dir
    for i in range(n_files):
        p = root / f"calc_f{i:02d}" / f"abc{i}" / "20240101_20240110.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"x": [i]}).to_parquet(p, index=False)


def test_cache_info_counts(tmp_path):
    cache_dir = tmp_path / "cache"
    _make_cache_files(cache_dir, n_files=4)
    result = runner.invoke(app, ["cache", "info", "--cache-dir", str(cache_dir)])
    assert result.exit_code == 0
    assert "4" in result.stdout  # 文件数
    assert "calc_f00" in result.stdout  # 按因子分组


def test_cache_info_json(tmp_path):
    cache_dir = tmp_path / "cache"
    _make_cache_files(cache_dir, n_files=2)
    result = runner.invoke(
        app, ["cache", "info", "--cache-dir", str(cache_dir), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file_count"] == 2
    assert payload["bytes"] > 0
    assert "by_factor" in payload


def test_cache_info_empty_dir(tmp_path):
    cache_dir = tmp_path / "empty"
    cache_dir.mkdir()
    result = runner.invoke(
        app, ["cache", "info", "--cache-dir", str(cache_dir), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file_count"] == 0


def test_cache_clear_all(tmp_path):
    cache_dir = tmp_path / "cache"
    _make_cache_files(cache_dir, n_files=3)
    result = runner.invoke(
        app, ["cache", "clear", "--cache-dir", str(cache_dir), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["removed"] == 3
    assert list(cache_dir.rglob("*.parquet")) == []


def test_cache_clear_single_factor(tmp_path):
    cache_dir = tmp_path / "cache"
    _make_cache_files(cache_dir, n_files=3)
    result = runner.invoke(
        app,
        ["cache", "clear", "--factor", "calc_f00", "--cache-dir", str(cache_dir)],
    )
    assert result.exit_code == 0
    assert "1" in result.stdout
    remaining = list(cache_dir.rglob("*.parquet"))
    assert len(remaining) == 2


def test_cache_clear_missing_dir(tmp_path):
    result = runner.invoke(
        app,
        ["cache", "clear", "--cache-dir", str(tmp_path / "absent")],
    )
    assert result.exit_code == 0
    assert "0" in result.stdout


def test_cache_clear_single_factor_json(tmp_path):
    cache_dir = tmp_path / "cache"
    _make_cache_files(cache_dir, n_files=3)
    result = runner.invoke(
        app,
        [
            "cache",
            "clear",
            "--factor",
            "calc_f01",
            "--cache-dir",
            str(cache_dir),
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["removed"] == 1


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
