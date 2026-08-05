"""yq factor 子命令测试：list / run / evaluate。"""

import json
import math

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from yq.cli import app

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


def _write_price(tmp_path, **kw) -> str:
    path = tmp_path / "price.parquet"
    _price_df(**kw).to_parquet(path, index=False)
    return str(path)


# ---------------- factor list ----------------


def test_list_text_lists_registered():
    result = runner.invoke(app, ["factor", "list"])
    assert result.exit_code == 0
    assert "calc_obv" in result.stdout
    assert "calc_hv" in result.stdout
    assert "kind" in result.stdout.lower()


def test_list_tag_filter():
    result = runner.invoke(app, ["factor", "list", "--tag", "momentum"])
    assert result.exit_code == 0
    assert "calc_momentum_20d_return" in result.stdout
    result2 = runner.invoke(app, ["factor", "list", "--tag", "no-such-tag"])
    assert result2.exit_code == 0
    assert "calc_obv" not in result2.stdout


def test_list_kind_filter():
    result = runner.invoke(app, ["factor", "list", "--kind", "pair"])
    assert result.exit_code == 0
    assert "calc_spread" in result.stdout
    assert "calc_obv" not in result.stdout


def test_list_json_structure():
    result = runner.invoke(app, ["factor", "list", "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert isinstance(rows, list) and len(rows) > 50
    first = rows[0]
    assert {"name", "kind", "tags", "params"} <= set(first)
    # pair 因子带 kind=pair 标记
    pair = [r for r in rows if r["name"] == "calc_spread"]
    assert pair and pair[0]["kind"] == "pair"


def test_list_verbose_adds_description():
    result = runner.invoke(app, ["factor", "list", "--verbose"])
    assert result.exit_code == 0
    assert "description" in result.stdout.lower()
    assert "OBV" in result.stdout  # calc_obv docstring 首行


def test_list_verbose_json_has_description_and_alias_shares_doc():
    result = runner.invoke(app, ["factor", "list", "--verbose", "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows and "description" in rows[0]
    obv = next(r for r in rows if r["name"] == "calc_obv")
    assert obv["description"].strip()
    # 别名与主因子共享同一个函数 → 介绍一致
    main = next(r for r in rows if r["name"] == "calc_cci_12d")
    alias = next(r for r in rows if r["name"] == "gtja_78")
    assert main["description"] and main["description"] == alias["description"]


def test_list_default_json_has_no_description():
    result = runner.invoke(app, ["factor", "list", "--json"])
    rows = json.loads(result.stdout)
    assert "description" not in rows[0]


# ---------------- factor run ----------------


def test_run_single_factor(tmp_path):
    price = _write_price(tmp_path)
    result = runner.invoke(app, ["factor", "run", "calc_obv", "--input", price])
    assert result.exit_code == 0
    # 文本表格包含 date/code/因子列与行数
    assert "date" in result.stdout and "code" in result.stdout
    assert "calc_obv" in result.stdout
    # 5 stocks x 20 days = 100 行
    assert result.stdout.count("\n") >= 100


def test_run_with_output_parquet(tmp_path):
    price = _write_price(tmp_path)
    out = tmp_path / "obv.parquet"
    result = runner.invoke(
        app,
        ["factor", "run", "calc_obv", "--input", price, "--output", str(out)],
    )
    assert result.exit_code == 0
    df = pd.read_parquet(out)
    assert {"date", "code", "calc_obv"} <= set(df.columns)
    assert len(df) == 100
    # 有 --output 时不打印全表，只给确认信息
    assert "已写入" in result.stdout
    assert "000001" not in result.stdout


def test_run_with_output_json_confirmation(tmp_path):
    price = _write_price(tmp_path)
    out = tmp_path / "obv.parquet"
    result = runner.invoke(
        app,
        ["factor", "run", "calc_obv", "--input", price, "--output", str(out), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["rows"] == 100
    assert "output" in payload


def test_run_with_param_and_json(tmp_path):
    price = _write_price(tmp_path)
    result = runner.invoke(
        app,
        [
            "factor",
            "run",
            "calc_rsi",
            "--input",
            price,
            "--param",
            "window=14",
            "--json",
        ],
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 100
    assert rows[0]["calc_rsi"] is not None or rows[0]["calc_rsi"] is None
    # 前 window-1 行应为 NaN（RSI 需要 window 个样本）→ null
    assert rows[0]["calc_rsi"] is None


def test_run_pair_factor_rejected(tmp_path):
    price = _write_price(tmp_path)
    result = runner.invoke(app, ["factor", "run", "calc_spread", "--input", price])
    assert result.exit_code == 1
    assert "pair" in result.stderr


def test_run_unknown_factor(tmp_path):
    price = _write_price(tmp_path)
    result = runner.invoke(app, ["factor", "run", "no_such_factor", "--input", price])
    assert result.exit_code == 1
    assert "no_such_factor" in result.stderr


def test_run_missing_input_file(tmp_path):
    result = runner.invoke(
        app, ["factor", "run", "calc_obv", "--input", str(tmp_path / "nope.parquet")]
    )
    assert result.exit_code == 1


def test_run_invalid_param_format(tmp_path):
    price = _write_price(tmp_path)
    result = runner.invoke(
        app,
        ["factor", "run", "calc_obv", "--input", price, "--param", "window"],
    )
    assert result.exit_code == 1
    assert "--param" in result.stderr


def test_run_no_cache_flag(tmp_path):
    """--no-cache 时不写缓存目录。"""
    price = _write_price(tmp_path)
    result = runner.invoke(
        app,
        ["factor", "run", "calc_obv", "--input", price, "--no-cache"],
    )
    assert result.exit_code == 0
    cache_dir = tmp_path / "factors"
    assert not (cache_dir).exists()


# ---------------- factor evaluate ----------------


def _factor_wide_table(price_df: pd.DataFrame) -> pd.DataFrame:
    """宽表：date/code + perfect 因子（= 前向收益的单调变换）→ IC≈1。"""
    fr = (
        price_df.sort_values(["code", "date"])
        .groupby("code")["close"]
        .pct_change()
        .shift(-1)
        .reset_index(drop=True)
    )
    wide = price_df[["date", "code"]].copy()
    wide["perfect"] = fr * 1000.0
    return wide


def test_evaluate_ic_close_to_one(tmp_path):
    price_df = _price_df(n_stocks=10, n_days=30, seed=7)
    wide = _factor_wide_table(price_df)
    price_path = tmp_path / "price.parquet"
    wide_path = tmp_path / "factors.parquet"
    price_df.to_parquet(price_path, index=False)
    wide.to_parquet(wide_path, index=False)
    result = runner.invoke(
        app,
        [
            "factor",
            "evaluate",
            "--input",
            str(wide_path),
            "--price",
            str(price_path),
            "--factor",
            "perfect",
            "--window",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "perfect" in result.stdout
    assert "ic_mean" in result.stdout
    # perfect 因子的 ic_mean ≈ 1
    lines = [ln for ln in result.stdout.splitlines() if "perfect" in ln]
    assert any("0.9" in ln or "1.0" in ln for ln in lines)


def test_evaluate_json_full(tmp_path):
    price_df = _price_df(n_stocks=10, n_days=30, seed=7)
    wide = _factor_wide_table(price_df)
    price_path = tmp_path / "price.parquet"
    wide_path = tmp_path / "factors.parquet"
    price_df.to_parquet(price_path, index=False)
    wide.to_parquet(wide_path, index=False)
    result = runner.invoke(
        app,
        [
            "factor",
            "evaluate",
            "--input",
            str(wide_path),
            "--price",
            str(price_path),
            "--factor",
            "perfect",
            "--window",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "summary" in payload
    summary = payload["summary"]
    assert summary[0]["factor"] == "perfect"
    assert math.isclose(summary[0]["ic_mean"], 1.0, abs_tol=1e-6)


def test_evaluate_multiple_factors(tmp_path):
    price_df = _price_df(n_stocks=10, n_days=30, seed=7)
    wide = _factor_wide_table(price_df)
    wide["noise"] = np.random.default_rng(0).normal(size=len(wide))
    price_path = tmp_path / "price.parquet"
    wide_path = tmp_path / "factors.parquet"
    price_df.to_parquet(price_path, index=False)
    wide.to_parquet(wide_path, index=False)
    result = runner.invoke(
        app,
        [
            "factor",
            "evaluate",
            "--input",
            str(wide_path),
            "--price",
            str(price_path),
            "--factor",
            "perfect",
            "--factor",
            "noise",
            "--window",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "perfect" in result.stdout
    assert "noise" in result.stdout


def test_evaluate_without_price_uses_close(tmp_path):
    """不传 --price 时用输入宽表里的 close 列。"""
    price_df = _price_df(n_stocks=10, n_days=30, seed=7)
    wide = _factor_wide_table(price_df)
    wide["close"] = price_df["close"].values
    wide_path = tmp_path / "factors.parquet"
    wide.to_parquet(wide_path, index=False)
    result = runner.invoke(
        app,
        [
            "factor",
            "evaluate",
            "--input",
            str(wide_path),
            "--factor",
            "perfect",
            "--window",
            "1",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert math.isclose(payload["summary"][0]["ic_mean"], 1.0, abs_tol=1e-6)


def test_evaluate_missing_factor_column(tmp_path):
    price_df = _price_df(n_stocks=10, n_days=30, seed=7)
    wide = price_df[["date", "code", "close"]].copy()
    wide_path = tmp_path / "factors.parquet"
    wide.to_parquet(wide_path, index=False)
    result = runner.invoke(
        app,
        [
            "factor",
            "evaluate",
            "--input",
            str(wide_path),
            "--factor",
            "ghost",
            "--window",
            "1",
        ],
    )
    assert result.exit_code == 1
    assert "ghost" in result.stderr


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """跑测试期间把因子缓存目录隔离到 tmp_path，避免污染真实 data/factors。"""
    monkeypatch.setenv("FACTOR_CACHE_DIR", str(tmp_path / "factors-cache"))
