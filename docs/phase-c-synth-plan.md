# Phase C：合成信号接入策略层实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase A 去冗余后的代表因子按等权 / IC 加权合成单一信号（date, code, signal, confidence），接入既有 backtest 管道，与"最佳单因子"对比回测——验证组合是否真正优于单因子。

**Architecture:** 纯函数落在 `factors/ops/synth.py`（`combine_factor_scores` / `scores_to_signals` / `compute_ic_weights`），编排与回测对比落在 `analysis/factor_synth.py::run_phase_c`（复用 Phase A 的 representatives 产物 + monitor 的 state 长表 + 全市场 ohlcv），CLI `yq factor clean-c` 接入，净值对比图追加到 `analysis/plot.py`。合成信号不改变 `strategies/` / `portfolio/` 模块本身——只新增"因子 → 合成信号"转换层，信号格式与既有 `Strategy.generate_signal` 输出一致（date, code, signal, confidence），回测走既有 `backtest.pipeline.run_pipeline`。

**Tech Stack:** Python 3.11+ / pandas / numpy / typer / matplotlib / pytest / ruff

## Global Constraints

- **项目铁律**：绝对 TDD（失败测试先行，禁止先实现后补测）；模块解耦（通过接口交互）；禁止生产代码 mock；中文 docstring
- **执行前置**：每个 task 开始前已 invoke `karpathy-guidelines`（项目规范，新 phase 必读）
- **环境**：`.venv/bin/python -m pytest`（`.venv/bin/pytest` shebang 陈旧）；`ruff` 用 `.venv/bin/python -m ruff`；全量回归 `pytest -q` 基线 **1119 passed**（Phase B 路径② 修正后实测）
- **commit 风格**：`feat(factors):` / `feat(analysis):` / `feat(yq):` / `docs:`，每个 task 独立 commit
- **只依赖这些既有模块**（不得新增依赖面）：`factors.registry.run_factor`（因子值，磁盘缓存）、`analysis.factor_monitor`（STATE_COLS）、`analysis.factor_clean._load_state` 同款 state 读取、`backtest.pipeline.run_pipeline`（回测）、`config/loader.py`（FACTOR_CLEAN_DEFAULTS / load_factor_clean_config）、`analysis.plot`（matplotlib 风格）
- **不耦合 `strategies/` 与 `portfolio/`**：Phase C 只产出与 Strategy 输出同格式的信号 DataFrame，回测直接走 `run_pipeline(signals, data)`；不注册新 Strategy 类、不改 allocator
- **信号格式**：`(date, code, signal, confidence)`，signal ∈ {1, -1, 0}（int）、confidence ∈ [0, 1]（float）——与 `Strategy.generate_signal` 契约一致（`strategies/base.py` docstring）
- **合成口径**：每日截面 rank 归一化（`rank(pct=True)`，0-1 分位）→ 加权平均；权重带符号（负 IC = 反向因子）；等权默认；IC 加权权重 = 各因子 as_of 前 `ic_lookback` 天 IC 均值（剔除 NaN），Σ|w| = 1
- **回测公平性**：合成信号与每个单因子信号用**完全相同**的 rebalance / top_n / bottom_n / capital / max_weight / dead_zone；"最佳单因子" = 各代表因子单独合成（单因子权重）后回测 metrics 中 sharpe_ratio 最高者
- **内存**：`full_market_ohlcv.parquet`（55MB）全量读 OK；因子宽表只保留 date/code + 代表因子列（Phase A 4 个代表 ≈ 4 float64 列 × 354 万行 ≈ 115MB 峰值，OK）；禁止全因子宽表
- **配置**：`configs/factor_clean.yaml` 新增 Phase C 段（synth_weighting: equal / synth_rebalance: 20 / synth_top_n: 10 / synth_bottom_n: 5 / ic_lookback: 60），`FACTOR_CLEAN_DEFAULTS` 同步 + 校验

---

## File Structure

| 文件 | 责任 |
|------|------|
| `src/factors/ops/synth.py`（新建） | Phase C 纯函数：`combine_factor_scores` / `scores_to_signals` / `compute_ic_weights` |
| `src/analysis/factor_synth.py`（新建） | `run_phase_c` 编排 + `compare_backtests` 回测对比 + representatives 解析 |
| `src/analysis/plot.py`（修改） | 追加 `plot_equity_compare`（净值对比图） |
| `src/config/loader.py`（修改） | `FACTOR_CLEAN_DEFAULTS` 加 5 项 + `load_factor_clean_config` 加校验 |
| `configs/factor_clean.yaml`（修改） | 追加 Phase C 配置段 |
| `src/yq/factors.py`（修改） | 追加 `factor_clean_c` 命令 |
| `tests/factors/test_synth.py`（新建） | 3 个纯函数的单测 |
| `tests/analysis/test_factor_synth.py`（新建） | run_phase_c / compare_backtests 集成测试 |
| `tests/analysis/test_plot.py`（修改） | `plot_equity_compare` 测试 |
| `tests/cli/test_clean_c_cmd.py`（新建） | CLI 测试 |
| `docs/data-schemas.md` / `docs/project-plan.md` / `docs/history.md` / `docs/factors-clean.md`（修改） | 契约同步 |

---

### Task 1: `combine_factor_scores` 合成得分（等权 + 带符号权重）

**Files:**
- Create: `src/factors/ops/synth.py`
- Test: `tests/factors/test_synth.py`

**Interfaces:**
- Consumes: 无（纯函数，只依赖 pandas/numpy）
- Produces: `combine_factor_scores(factor_df, factors, weights=None) -> pd.Series`——Task 4 的 run_phase_c 消费；`factor_df` 为宽表（date/code + 因子列），`weights` 带符号（负 = 反向因子），None = 等权；返回与 `factor_df` 行对齐的 `pd.Series`，name="synth_score"，某行全部因子 NaN 时该行 NaN

- [ ] **Step 1: Write the failing test**

```python
"""tests/factors/test_synth.py — Phase C 合成信号纯函数单测（Task 1-3 共用文件）。"""
import numpy as np
import pandas as pd
import pytest

from factors.ops.synth import combine_factor_scores, compute_ic_weights, scores_to_signals


# ---------------------------------------------------------------------------
# Task 1: combine_factor_scores
# ---------------------------------------------------------------------------


def test_combine_scores_equal_weight_daily_cross_section():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3 + ["2024-01-03"] * 3,
            "code": ["A", "B", "C"] * 2,
            "f1": [1.0, 2.0, 3.0, 3.0, 1.0, 2.0],
            "f2": [3.0, 1.0, 2.0, 1.0, 3.0, 2.0],
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    # 01-02: f1 rank=[1/3,2/3,1], f2 rank=[1,1/3,2/3] → avg=[2/3,1/2,5/6]
    # 01-03: f1 rank=[2/3,1/3,1]? 不：f1=[3,1,2] → rank=[1,1/3,2/3]
    #        f2=[1,3,2] → rank=[1/3,1,2/3] → avg=[2/3,2/3,2/3]
    expected = pd.Series(
        [2 / 3, 1 / 2, 5 / 6, 2 / 3, 2 / 3, 2 / 3],
        index=df.index,
        name="synth_score",
    )
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_with_symbolic_weights():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3,
            "code": ["A", "B", "C"],
            "f1": [1.0, 2.0, 3.0],   # rank=[1/3,2/3,1]
            "f2": [3.0, 1.0, 2.0],   # rank=[1,1/3,2/3]
        }
    )
    # f1 权重 +2（正向），f2 权重 -1（反向 → 用 1-rank）
    score = combine_factor_scores(df, ["f1", "f2"], weights={"f1": 2.0, "f2": -1.0})
    # eff_f1=[1/3,2/3,1], eff_f2=[0,2/3,1/3]（1-rank）
    # num = 2*eff_f1 + 1*eff_f2 = [2/3, 2, 7/3]
    # den = 3 → score = [2/9, 2/3, 7/9]
    expected = pd.Series([2 / 9, 2 / 3, 7 / 9], index=df.index, name="synth_score")
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_all_nan_row_is_nan():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "code": ["A", "B"],
            "f1": [1.0, np.nan],
            "f2": [2.0, np.nan],
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    assert np.isnan(score.iloc[1])
    assert not np.isnan(score.iloc[0])


def test_combine_scores_partial_nan_row_reweights():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "code": ["A", "B"],
            "f1": [1.0, 2.0],   # rank=[0.5,1]
            "f2": [np.nan, 1.0],  # B 行有效
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    # A 行只有 f1 有效 → 分母=1 → 0.5
    # B 行两因子有效 → avg(1, 1)=1
    expected = pd.Series([0.5, 1.0], index=df.index, name="synth_score")
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_empty_factors_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"], "f1": [1.0]})
    with pytest.raises(ValueError):
        combine_factor_scores(df, [])


def test_combine_scores_missing_column_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"], "f1": [1.0]})
    with pytest.raises(ValueError):
        combine_factor_scores(df, ["f1", "f_missing"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'factors.ops.synth'`）

- [ ] **Step 3: Write minimal implementation**

```python
"""factors/ops/synth.py — Phase C 合成信号纯函数。

把多个因子（通常是 Phase A 去冗余后的代表因子）合成单一信号：
每日截面 rank 归一化 → 带符号权重加权平均 → 综合得分。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def combine_factor_scores(
    factor_df: pd.DataFrame,
    factors: list[str],
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """每日截面 rank 归一化 → 加权平均 → 综合得分。

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date``、``code`` 与 ``factors`` 列。
    factors : list[str]
        参与合成的因子列名。
    weights : dict[str, float] | None
        因子权重（带符号：负权重 = 反向因子，内部用 1-rank）。
        None = 等权。

    Returns
    -------
    Series
        与 ``factor_df`` 行对齐的综合得分，name="synth_score"；
        某行全部因子为 NaN 时为 NaN。
    """
    if not factors:
        raise ValueError("factors 不能为空")
    missing = [f for f in factors if f not in factor_df.columns]
    if missing:
        raise ValueError(f"factor_df 缺少列: {missing}")
    if weights is None:
        weights = {f: 1.0 for f in factors}

    # 每日截面 rank（pct 0-1）
    ranks = pd.DataFrame(
        {f: factor_df.groupby("date")[f].rank(pct=True) for f in factors}
    )
    w = np.array([weights.get(f, 0.0) for f in factors], dtype=float)
    dirs = np.sign(w)
    mags = np.abs(w)

    eff = ranks.to_numpy(dtype=float)
    for i, f in enumerate(factors):
        if dirs[i] < 0:
            eff[:, i] = 1.0 - eff[:, i]

    valid = ~np.isnan(eff)
    num = np.nansum(eff * mags[None, :], axis=1)
    den = np.where(valid, mags[None, :], 0.0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    return pd.Series(score, index=factor_df.index, name="synth_score")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/synth.py tests/factors/test_synth.py
git commit -m "feat(factors): 合成信号纯函数 combine_factor_scores（每日截面 rank + 带符号加权）"
```

---

### Task 2: `scores_to_signals` 得分 → 信号

**Files:**
- Modify: `src/factors/ops/synth.py`
- Test: `tests/factors/test_synth.py`

**Interfaces:**
- Consumes: Task 1 的 `combine_factor_scores` 输出（score Series，与 `factor_df` 行对齐）
- Produces: `scores_to_signals(factor_df, score, *, rebalance=20, top_n=10, bottom_n=5) -> pd.DataFrame`——Task 4 消费；返回 `(date, code, signal, confidence)`，signal ∈ {1,-1,0}（int）、confidence ∈ [0,1]；每个再平衡日截面得分 top_n → signal=1（confidence=得分），bottom_n → signal=-1（confidence=0.5），持仓延续到下一再平衡日，前一期持仓未再买入的股票在再平衡日卖出

- [ ] **Step 1: Write the failing test**

```python
# ---------------------------------------------------------------------------
# Task 2: scores_to_signals
# ---------------------------------------------------------------------------


def test_scores_to_signals_basic_rebalance_rotation():
    dates = pd.bdate_range("2024-01-02", periods=6)
    rows = []
    for d in dates:
        for c in ["A", "B", "C"]:
            rows.append({"date": d, "code": c})
    df = pd.DataFrame(rows)
    # 截面得分：A 最高、C 最低（每个交易日相同）
    score = pd.Series([0.9, 0.5, 0.1] * 6, index=df.index)
    out = scores_to_signals(df, score, rebalance=3, top_n=1, bottom_n=1)
    assert list(out.columns) == ["date", "code", "signal", "confidence"]
    assert out["signal"].dtype == int
    assert out["confidence"].dtype == float
    # 第一期（第 0-2 天）：买入 A（signal=1, confidence=0.9），卖出 C（signal=-1, 0.5）
    first = out.iloc[:6]
    a_signals = first[first["code"] == "A"]["signal"].tolist()
    assert a_signals == [1, 1, 1]
    c_signals = first[first["code"] == "C"]["signal"].tolist()
    assert c_signals == [-1, -1, -1]
    b_signals = first[first["code"] == "B"]["signal"].tolist()
    assert b_signals == [0, 0, 0]
    a_conf = first[first["code"] == "A"]["confidence"].tolist()
    assert all(abs(v - 0.9) < 1e-9 for v in a_conf)


def test_scores_to_signals_nan_scores_not_selected():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3,
            "code": ["A", "B", "C"],
        }
    )
    score = pd.Series([0.9, np.nan, 0.1], index=df.index)
    out = scores_to_signals(df, score, rebalance=1, top_n=1, bottom_n=1)
    assert out.loc[out["code"] == "A", "signal"].iloc[0] == 1
    assert out.loc[out["code"] == "B", "signal"].iloc[0] == 0  # NaN 不入选
    assert out.loc[out["code"] == "C", "signal"].iloc[0] == -1


def test_scores_to_signals_top_bottom_zero_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"]})
    score = pd.Series([0.5], index=df.index)
    with pytest.raises(ValueError):
        scores_to_signals(df, score, rebalance=1, top_n=0, bottom_n=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: FAIL（`NameError: name 'scores_to_signals' is not defined`）

- [ ] **Step 3: Write minimal implementation**

```python
def scores_to_signals(
    factor_df: pd.DataFrame,
    score: pd.Series,
    *,
    rebalance: int = 20,
    top_n: int = 10,
    bottom_n: int = 5,
) -> pd.DataFrame:
    """综合得分 → (date, code, signal, confidence)。

    每个再平衡日：截面得分排序 → top_n 买入（signal=1，confidence=得分）
    → bottom_n 卖出（signal=-1，confidence=0.5）；持仓延续到下一再平衡日；
    前一期持仓未再买入的股票在再平衡日卖出。得分 NaN 的股票不入选。

    Parameters
    ----------
    factor_df : DataFrame
        含 ``date``、``code`` 列（与 score 行对齐）。
    score : Series
        综合得分（与 factor_df 行对齐）。
    rebalance : int
        再平衡周期（交易日）。
    top_n / bottom_n : int
        每期买入/卖出股票数。二者不能同时为 0。

    Returns
    -------
    DataFrame
        列：date, code, signal（int 1/-1/0）, confidence（float）。
    """
    if top_n <= 0 and bottom_n <= 0:
        raise ValueError("top_n 与 bottom_n 至少一个 > 0")
    df = factor_df[["date", "code"]].copy()
    df["__score__"] = score.to_numpy(dtype=float)
    dates = sorted(df["date"].unique())

    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)
    prev_holdings: set[str] = set()

    for i in range(0, len(dates), rebalance):
        rb_date = dates[i]
        nxt = min(i + rebalance, len(dates))
        hold_dates = dates[i:nxt]

        day = df[df["date"] == rb_date].dropna(subset=["__score__"])
        day = day.sort_values("__score__", ascending=False)
        buys = set(day.head(top_n)["code"]) if top_n > 0 else set()
        sells = set(day.tail(bottom_n)["code"]) if bottom_n > 0 else set()
        score_by_code = dict(zip(day["code"], day["__score__"]))

        for hd in hold_dates:
            h_mask = df["date"] == hd
            for c in buys:
                m = h_mask & (df["code"] == c)
                signal[m] = 1
                confidence[m] = float(score_by_code.get(c, 0.5))
            for c in sells - buys:
                m = h_mask & (df["code"] == c)
                signal[m] = -1
                confidence[m] = 0.5
        # 退出持仓：上一期买入但本期未买入 → 在再平衡日卖出
        for c in prev_holdings - buys:
            m = (df["date"] == rb_date) & (df["code"] == c)
            signal[m] = -1
            confidence[m] = 0.5
        prev_holdings = buys

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/synth.py tests/factors/test_synth.py
git commit -m "feat(factors): scores_to_signals 得分转信号（rebalance 轮动，仿 multifactor_signal）"
```

---

### Task 3: `compute_ic_weights` IC 加权权重

**Files:**
- Modify: `src/factors/ops/synth.py`
- Test: `tests/factors/test_synth.py`

**Interfaces:**
- Consumes: monitor state 长表（STATE_COLS，含 date/factor/fwd_window/ic）
- Produces: `compute_ic_weights(state, factors, *, as_of, fwd_window=5, lookback=60) -> dict[str, float]`——Task 4 消费；返回 `{factor: weight}`，权重带符号（负 IC 均值 = 反向因子），Σ|w| = 1；因子 IC 全 NaN 或无效 → 权重 0；全部无效 → 等权

- [ ] **Step 1: Write the failing test**

```python
# ---------------------------------------------------------------------------
# Task 3: compute_ic_weights
# ---------------------------------------------------------------------------


def test_ic_weights_from_state_mean_ic_with_sign():
    dates = pd.bdate_range("2024-01-01", periods=10)
    rows = []
    for d in dates:
        rows.append(
            {
                "date": d,
                "factor": "f_positive",
                "fwd_window": 5,
                "ic": 0.03,
                "rolling_ic": 0.03,
                "rolling_ir": 0.5,
                "t_stat": 3.0,
                "state": "active",
                "sustain_days": 10,
            }
        )
        rows.append(
            {
                "date": d,
                "factor": "f_negative",
                "fwd_window": 5,
                "ic": -0.01,
                "rolling_ic": -0.01,
                "rolling_ir": -0.2,
                "t_stat": -1.5,
                "state": "active",
                "sustain_days": 10,
            }
        )
    state = pd.DataFrame(rows)
    w = compute_ic_weights(
        state, ["f_positive", "f_negative"], as_of=pd.Timestamp("2024-01-10")
    )
    # mean(ic) = [0.03, -0.01] → w = [0.03/0.04, -0.01/0.04] = [0.75, -0.25]
    assert abs(w["f_positive"] - 0.75) < 1e-9
    assert abs(w["f_negative"] + 0.25) < 1e-9


def test_ic_weights_lookback_trims_and_na_skips():
    dates = pd.bdate_range("2024-01-01", periods=70)
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "date": d,
                "factor": "f",
                "fwd_window": 5,
                "ic": 0.02 if i >= 10 else np.nan,  # 前 10 天 NaN
                "rolling_ic": 0.02,
                "rolling_ir": 0.4,
                "t_stat": 2.0,
                "state": "active",
                "sustain_days": 10,
            }
        )
    state = pd.DataFrame(rows)
    w = compute_ic_weights(state, ["f"], as_of=pd.Timestamp("2024-03-01"), lookback=30)
    # 有效 ic 共 60 天，tail(30) → 30 个 0.02 → mean=0.02 → 单因子 w=1.0
    assert abs(w["f"] - 1.0) < 1e-9


def test_ic_weights_all_invalid_falls_back_to_equal():
    state = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 2,
            "factor": ["f1", "f2"],
            "fwd_window": [5, 5],
            "ic": [np.nan, np.nan],
            "rolling_ic": [np.nan, np.nan],
            "rolling_ir": [np.nan, np.nan],
            "t_stat": [np.nan, np.nan],
            "state": ["active", "active"],
            "sustain_days": [1, 1],
        }
    )
    w = compute_ic_weights(state, ["f1", "f2"], as_of=pd.Timestamp("2024-01-02"))
    assert w == {"f1": 0.5, "f2": 0.5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: FAIL（`NameError: name 'compute_ic_weights' is not defined`）

- [ ] **Step 3: Write minimal implementation**

```python
def compute_ic_weights(
    state: pd.DataFrame,
    factors: list[str],
    *,
    as_of: pd.Timestamp,
    fwd_window: int = 5,
    lookback: int = 60,
) -> dict[str, float]:
    """state 长表 → 各因子 IC 均值权重（带符号，Σ|w|=1）。

    每个因子取 ``as_of`` 之前 ``lookback`` 天的 ``ic`` 均值（剔除 NaN）；
    IC 均值为负 → 权重负（反向因子）。全部无效 → 等权兜底。

    Parameters
    ----------
    state : DataFrame
        monitor 的 state 长表（STATE_COLS）。
    factors : list[str]
        参与合成的因子名。
    as_of : Timestamp
        权重评估截止日（只用其及之前的数据，无未来信息）。
    fwd_window : int
        取 state 中该 forward 窗口的 IC 行。
    lookback : int
        取最近多少个交易日的 IC 均值。

    Returns
    -------
    dict[str, float]
        {factor: weight}，Σ|w| = 1。
    """
    if not factors:
        raise ValueError("factors 不能为空")
    means: dict[str, float] = {}
    for f in factors:
        sub = state[
            (state["factor"] == f)
            & (state["fwd_window"] == fwd_window)
            & (state["date"] <= as_of)
        ]["ic"].dropna().tail(lookback)
        means[f] = float(sub.mean()) if len(sub) > 0 else 0.0
    total = sum(abs(v) for v in means.values())
    if total == 0:
        return {f: 1.0 / len(factors) for f in factors}
    return {f: means[f] / total for f in factors}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_synth.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/synth.py tests/factors/test_synth.py
git commit -m "feat(factors): compute_ic_weights IC 加权权重（带符号，Σ|w|=1）"
```

---

### Task 4: `run_phase_c` 编排 + 回测对比

**Files:**
- Create: `src/analysis/factor_synth.py`
- Test: `tests/analysis/test_factor_synth.py`

**Interfaces:**
- Consumes: Task 1-3 的 3 个纯函数；`factors.registry.run_factor`；`backtest.pipeline.run_pipeline`；monitor state（STATE_COLS）；Phase A representatives（`representatives.json` 或 list[str]）
- Produces:
  - `run_phase_c(*, state_path, ohlcv_path, representatives, synth_weighting="equal", fwd_window=5, ic_lookback=60, rebalance=20, top_n=10, bottom_n=5, cache_dir=None, use_cache=True, output_dir=None, capital=1_000_000, max_weight=0.3, dead_zone=0.015) -> dict`——Task 6 CLI 消费；返回 `{signals, compare, equity_curves, summary}`；output_dir 给定时写 `synth_signals.parquet` / `backtest_compare.parquet` / `equity_compare.png` / `summary.json`
  - `compare_backtests(signals_map, data, *, capital, max_weight, dead_zone) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]`——metrics 对比表（index=strategy）与净值曲线 dict
  - `_resolve_representatives(rep) -> list[str]`——list 原样返回；Path/str 读 JSON 取 `representatives[].representative`

- [ ] **Step 1: Write the failing test**

```python
"""tests/analysis/test_factor_synth.py — Phase C 编排集成测试。"""
import json

import numpy as np
import pandas as pd
import pytest

from analysis.factor_monitor import STATE_COLS
from analysis.factor_synth import _resolve_representatives, compare_backtests, run_phase_c


def _ohlcv(n_days=40, n_stocks=20, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for c in [f"{600000 + i}" for i in range(n_stocks)]:
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": c, "open": close - 0.05,
                    "high": close + 0.1, "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _state(tmp_path, factors=("calc_momentum_5d_change", "calc_volume_ratio")):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-06-02", periods=40)
    rows = []
    for d in dates:
        for name in factors:
            rows.append(
                {
                    "date": d, "factor": name, "fwd_window": 5,
                    "ic": float(rng.normal(0.02, 0.03)),
                    "rolling_ic": 0.02, "rolling_ir": 0.4,
                    "t_stat": 3.0, "state": "active", "sustain_days": 30,
                }
            )
    df = pd.DataFrame(rows, columns=STATE_COLS)
    p = tmp_path / "state.parquet"
    df.to_parquet(p)
    return p


def test_compare_backtests_returns_metrics_table(tmp_path):
    data = _ohlcv(n_days=30, n_stocks=10)
    sig = pd.DataFrame(
        {
            "date": data["date"],
            "code": data["code"],
            "signal": 1,
            "confidence": 0.5,
        }
    )
    compare, curves = compare_backtests(
        {"synth": sig, "single": sig}, data, capital=100_000, dead_zone=0.0
    )
    assert list(compare.index) == ["synth", "single"]
    for col in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "trade_count"):
        assert col in compare.columns
    assert "synth" in curves and "single" in curves
    assert "equity" in curves["synth"].columns


def test_run_phase_c_equal_weight_end_to_end(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out = run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        synth_weighting="equal",
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
    )
    sig = out["signals"]
    assert list(sig.columns) == ["date", "code", "signal", "confidence"]
    assert sig["signal"].isin([-1, 0, 1]).all()
    assert set(sig["code"].unique()) <= set(
        pd.read_parquet(ohlcv)["code"].unique()
    )
    assert "compare" in out and "equity_curves" in out and "summary" in out
    assert out["summary"]["synth_weighting"] == "equal"


def test_run_phase_c_ic_weighted_and_output_dir(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out_dir = tmp_path / "out"
    out = run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        synth_weighting="ic_weighted",
        ic_lookback=20,
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
        output_dir=out_dir,
    )
    assert (out_dir / "synth_signals.parquet").exists()
    assert (out_dir / "backtest_compare.parquet").exists()
    assert (out_dir / "equity_compare.png").exists()
    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["synth_weighting"] == "ic_weighted"
    assert "best_single" in summary


def test_run_phase_c_best_single_and_beats_flag(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out = run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
    )
    s = out["summary"]
    assert "best_single" in s and "best_single_sharpe" in s
    assert "synth_sharpe" in s and "synth_beats_best_single" in s
    assert isinstance(s["synth_beats_best_single"], bool)


def test_resolve_representatives(tmp_path):
    assert _resolve_representatives(["a", "b"]) == ["a", "b"]
    p = tmp_path / "reps.json"
    p.write_text(
        json.dumps(
            {
                "representatives": [
                    {"cluster_id": 0, "representative": "a", "members": ["a"]},
                    {"cluster_id": 1, "representative": "b", "members": ["b"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _resolve_representatives(p) == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/analysis/test_factor_synth.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'analysis.factor_synth'`）

- [ ] **Step 3: Write minimal implementation**

```python
"""analysis/factor_synth.py — Phase C 编排（analysis 层）。

读 Phase A 代表因子 + monitor state + 全市场 ohlcv → 合成信号 →
与各单因子回测对比（相同参数）→ 输出信号 / 对比表 / 净值图 / summary。
只读 monitor 产物与 Phase A 产物，不重算 IC/状态/相关。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.factor_monitor import STATE_COLS
from backtest.pipeline import run_pipeline
from factors.ops.synth import combine_factor_scores, compute_ic_weights, scores_to_signals
from factors.registry import run_factor


def _load_state(state_path: Path) -> pd.DataFrame:
    path = Path(state_path)
    if not path.exists():
        raise FileNotFoundError(f"state 文件不存在: {path}")
    df = pd.read_parquet(path)
    if not set(STATE_COLS).issubset(df.columns):
        raise ValueError(f"state.parquet 缺少列，需要 {STATE_COLS}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _resolve_representatives(rep: list[str] | str | Path) -> list[str]:
    """把代表因子输入归一化为因子名列表。

    list 原样返回；Path/str 视为 Phase A 的 representatives.json
    （含 ``representatives`` 键，每项取 ``representative`` 字段）。
    """
    if isinstance(rep, (str, Path)):
        payload = json.loads(Path(rep).read_text(encoding="utf-8"))
        return [r["representative"] for r in payload["representatives"]]
    return list(rep)


def compare_backtests(
    signals_map: dict[str, pd.DataFrame],
    data: pd.DataFrame,
    *,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    dead_zone: float = 0.015,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """多个信号各跑一遍 run_pipeline，返回 (metrics 对比表, 净值曲线 dict)。

    Parameters
    ----------
    signals_map : dict[str, DataFrame]
        {名称: (date, code, signal, confidence)}。
    data : DataFrame
        全市场行情（run_pipeline 的可交易性过滤/价格提取/引擎数据）。

    Returns
    -------
    (compare, curves)
        compare：index=strategy，列 = metrics（total_return / annual_return /
        sharpe_ratio / max_drawdown / win_rate / trade_count / total_cost /
        cost_ratio）。
        curves：{strategy: equity_curve DataFrame(date, equity, ...)}。
    """
    rows: list[dict] = []
    curves: dict[str, pd.DataFrame] = {}
    for name, sig in signals_map.items():
        res = run_pipeline(
            sig, data, capital, max_weight=max_weight, dead_zone=dead_zone
        )
        rows.append({"strategy": name, **res["metrics"]})
        curves[name] = res["equity_curve"]
    return pd.DataFrame(rows).set_index("strategy"), curves


def run_phase_c(
    *,
    state_path: Path,
    ohlcv_path: Path,
    representatives: list[str] | str | Path,
    synth_weighting: str = "equal",
    fwd_window: int = 5,
    ic_lookback: int = 60,
    rebalance: int = 20,
    top_n: int = 10,
    bottom_n: int = 5,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    output_dir: Path | None = None,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    dead_zone: float = 0.015,
) -> dict:
    """Phase C 编排：代表因子 → 合成信号 → 与单因子对比回测。

    Parameters
    ----------
    state_path : Path
        monitor 输出的 state.parquet（STATE_COLS 长表，IC 权重用）。
    ohlcv_path : Path
        全市场行情 parquet（date/code/close/...，含状态列）。
    representatives : list[str] | Path
        代表因子名单，或 Phase A representatives.json 路径。
    synth_weighting : str
        "equal"（默认）| "ic_weighted"。
    fwd_window : int
        IC 权重取 state 中该 forward 窗口的 IC 行。
    ic_lookback : int
        IC 权重评估窗口（交易日）。
    rebalance / top_n / bottom_n
        信号生成参数（透传 scores_to_signals）。
    cache_dir / use_cache
        透传给 run_factor。
    output_dir : Path | None
        给定时写 synth_signals.parquet / backtest_compare.parquet /
        equity_compare.png / summary.json。
    capital / max_weight / dead_zone
        回测参数（所有策略一致，保证对比公平）。

    Returns
    -------
    dict
        键：signals（合成信号）/ compare（对比表）/ equity_curves /
        summary（synth_weighting / best_single / synth_sharpe /
        synth_beats_best_single 等）。
    """
    if synth_weighting not in {"equal", "ic_weighted"}:
        raise ValueError(f"synth_weighting 非法: {synth_weighting!r}")
    factors = _resolve_representatives(representatives)
    if not factors:
        raise ValueError("representatives 解析为空")

    state = _load_state(state_path)
    as_of = state["date"].max()
    data = pd.read_parquet(ohlcv_path)
    data["date"] = pd.to_datetime(data["date"])

    # 因子值：只保留 date/code + 代表因子列
    base = data[["date", "code"]].copy()
    factor_df = base.copy()
    for f in factors:
        try:
            factor_df[f] = run_factor(f, data, cache_dir=cache_dir, use_cache=use_cache).to_numpy()
        except KeyError:
            factor_df[f] = float("nan")

    # 权重
    if synth_weighting == "equal":
        weights = None
    else:
        weights = compute_ic_weights(
            state, factors, as_of=as_of, fwd_window=fwd_window, lookback=ic_lookback
        )

    # 合成信号
    score = combine_factor_scores(factor_df, factors, weights=weights)
    synth_sig = scores_to_signals(
        factor_df, score, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n
    )

    # 单因子信号（同参数，保证对比公平）
    signals_map: dict[str, pd.DataFrame] = {"synth": synth_sig}
    for f in factors:
        if factor_df[f].notna().sum() < 2:
            continue  # 缺列/全 NaN 的因子不参与对比
        single_score = combine_factor_scores(factor_df, [f])
        signals_map[f] = scores_to_signals(
            factor_df, single_score, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n
        )

    compare, curves = compare_backtests(
        signals_map, data, capital=capital, max_weight=max_weight, dead_zone=dead_zone
    )

    synth_sharpe = float(compare.loc["synth", "sharpe_ratio"])
    singles = compare.drop(index="synth")
    best_name = singles["sharpe_ratio"].idxmax() if len(singles) > 0 else None
    best_sharpe = (
        float(singles.loc[best_name, "sharpe_ratio"]) if best_name is not None else 0.0
    )
    summary = {
        "synth_weighting": synth_weighting,
        "representatives": factors,
        "rebalance": rebalance,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "synth_sharpe": synth_sharpe,
        "best_single": best_name,
        "best_single_sharpe": best_sharpe,
        "synth_beats_best_single": bool(synth_sharpe >= best_sharpe),
    }

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        synth_sig.to_parquet(out / "synth_signals.parquet", index=False)
        compare.to_parquet(out / "backtest_compare.parquet")
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        from analysis.plot import plot_equity_compare

        plot_equity_compare(curves).savefig(
            out / "equity_compare.png", dpi=110, bbox_inches="tight"
        )

    return {
        "signals": synth_sig,
        "compare": compare,
        "equity_curves": curves,
        "summary": summary,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/analysis/test_factor_synth.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/analysis/factor_synth.py tests/analysis/test_factor_synth.py
git commit -m "feat(analysis): Phase C 编排 run_phase_c + compare_backtests 回测对比"
```

---

### Task 5: 净值对比图 + 配置 + CLI

**Files:**
- Modify: `src/analysis/plot.py`、`src/config/loader.py`、`configs/factor_clean.yaml`、`src/yq/factors.py`
- Test: `tests/analysis/test_plot.py`（修改）、`tests/cli/test_clean_c_cmd.py`（新建）

**Interfaces:**
- Consumes: Task 4 的 `run_phase_c`（CLI 调用）；`FACTOR_CLEAN_DEFAULTS`（配置）
- Produces:
  - `plot_equity_compare(curves: dict[str, pd.DataFrame]) -> matplotlib.figure.Figure`——净值对比图（Task 4 已引用）
  - `FACTOR_CLEAN_DEFAULTS` 新增 5 键：synth_weighting="equal" / synth_rebalance=20 / synth_top_n=10 / synth_bottom_n=5 / ic_lookback=60；`load_factor_clean_config` 校验 synth_weighting ∈ {equal, ic_weighted}、其余为正整数
  - CLI `yq factor clean-c`（参数见 Step 3）

- [ ] **Step 1: Write the failing test（plot）**

在 `tests/analysis/test_plot.py` 追加：

```python
def test_plot_equity_compare_normalizes_and_labels():
    import matplotlib
    matplotlib.use("Agg")
    import pandas as pd

    from analysis.plot import plot_equity_compare

    dates = pd.bdate_range("2024-01-01", periods=10)
    curves = {
        "synth": pd.DataFrame(
            {"date": dates, "equity": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]}
        ),
        "single": pd.DataFrame(
            {"date": dates, "equity": [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]}
        ),
    }
    fig = plot_equity_compare(curves)
    assert len(fig.axes) == 1
    ax = fig.axes[0]
    # 两条线，legend 两个标签
    assert len(ax.lines) == 2
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["synth", "single"]
    # 归一化到初始 1.0
    assert ax.lines[0].get_ydata()[0] == 1.0
    assert ax.lines[1].get_ydata()[0] == 1.0
    import matplotlib.pyplot as plt

    plt.close(fig)
```

Run: `.venv/bin/python -m pytest tests/analysis/test_plot.py::test_plot_equity_compare_normalizes_and_labels -q`
Expected: FAIL（`ImportError: cannot import name 'plot_equity_compare'`）

- [ ] **Step 2: Write minimal implementation（plot）**

在 `src/analysis/plot.py` 末尾追加：

```python
def plot_equity_compare(
    curves: dict[str, pd.DataFrame],
) -> matplotlib.figure.Figure:
    """多条净值曲线对比（归一化到初始 1.0）。

    Parameters
    ----------
    curves : dict[str, DataFrame]
        {策略名: (date, equity, ...)}。

    Returns
    -------
    Figure
        单轴图：x=日期，y=净值（初始=1.0），图例为策略名。
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    for name, eq in curves.items():
        if len(eq) == 0:
            continue
        norm = eq["equity"] / eq["equity"].iloc[0]
        ax.plot(pd.to_datetime(eq["date"]), norm, label=name)
    ax.set_xlabel("日期")
    ax.set_ylabel("净值（初始 = 1.0）")
    ax.set_title("合成信号 vs 单因子净值对比")
    ax.legend()
    ax.grid(alpha=0.3)
    return fig
```

Run: `.venv/bin/python -m pytest tests/analysis/test_plot.py::test_plot_equity_compare_normalizes_and_labels -q`
Expected: PASS

- [ ] **Step 3: 配置 + 校验（先测试）**

在 `tests/cli/test_clean_c_cmd.py` 新建（同时覆盖配置校验与 CLI）：

```python
"""tests/cli/test_clean_c_cmd.py — yq factor clean-c CLI 测试。"""
import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from analysis.factor_monitor import STATE_COLS
from yq.cli import app

runner = CliRunner()


def _ohlcv(n_days=30, n_stocks=10, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for c in [f"{600000 + i}" for i in range(n_stocks)]:
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": c, "open": close - 0.05,
                    "high": close + 0.1, "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _state(tmp_path):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-06-02", periods=30)
    rows = []
    for d in dates:
        for name in ("calc_momentum_5d_change", "calc_volume_ratio"):
            rows.append(
                {
                    "date": d, "factor": name, "fwd_window": 5,
                    "ic": float(rng.normal(0.02, 0.03)),
                    "rolling_ic": 0.02, "rolling_ir": 0.4,
                    "t_stat": 3.0, "state": "active", "sustain_days": 30,
                }
            )
    df = pd.DataFrame(rows, columns=STATE_COLS)
    p = tmp_path / "state.parquet"
    df.to_parquet(p)
    return p


def test_clean_c_runs_and_json(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    result = runner.invoke(
        app, [
            "factor", "clean-c",
            "--state", str(state), "--data", str(ohlcv),
            "--representatives", "calc_momentum_5d_change,calc_volume_ratio",
            "--rebalance", "5", "--top-n", "3", "--bottom-n", "2",
            "--capital", "100000", "--dead-zone", "0",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "synth_sharpe" in payload
    assert "best_single" in payload
    assert "synth_beats_best_single" in payload


def test_clean_c_invalid_weighting_exits_1(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    result = runner.invoke(
        app, [
            "factor", "clean-c",
            "--state", str(state), "--data", str(ohlcv),
            "--representatives", "calc_momentum_5d_change",
            "--weighting", "bogus",
        ]
    )
    assert result.exit_code != 0
    assert "错误" in result.output
```

Run: `.venv/bin/python -m pytest tests/cli/test_clean_c_cmd.py -q`
Expected: FAIL（`No such command: 'clean-c'`）——配置校验测试在 loader 里补（Step 5 实现后一起绿）

- [ ] **Step 4: 实现 CLI（先跑测试到 CLI 绿）**

`src/config/loader.py` 的 `FACTOR_CLEAN_DEFAULTS` 追加：

```python
    # Phase C（合成信号）
    "synth_weighting": "equal",
    "synth_rebalance": 20,
    "synth_top_n": 10,
    "synth_bottom_n": 5,
    "ic_lookback": 60,
```

`load_factor_clean_config` 校验块末尾追加：

```python
    if cfg["synth_weighting"] not in {"equal", "ic_weighted"}:
        raise ValueError(f"synth_weighting 非法: {cfg['synth_weighting']!r}")
    for key in ("synth_rebalance", "synth_top_n", "synth_bottom_n", "ic_lookback"):
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(f"{key} 必须为正整数，收到 {cfg[key]!r}")
```

`configs/factor_clean.yaml` 末尾追加：

```yaml
# Phase C 合成信号（对应 Q4）
synth_weighting: equal   # equal | ic_weighted（IC 加权更优但更易过拟合）
synth_rebalance: 20      # 信号再平衡周期（交易日）
synth_top_n: 10          # 每期买入股票数
synth_bottom_n: 5        # 每期卖出股票数
ic_lookback: 60          # IC 加权权重评估窗口（交易日）
```

`src/yq/factors.py` 追加（import 行加 `from analysis.factor_synth import run_phase_c`，并在 `factor_clean_b` 之后追加）：

```python
@factor_app.command("clean-c")
def factor_clean_c(
    state: Path = typer.Option(..., "--state", help="monitor 输出的 state.parquet"),
    data: Path = typer.Option(..., "--data", help="全市场行情 parquet"),
    representatives: str = typer.Option(
        ..., "--representatives",
        help="代表因子名（逗号分隔）或 Phase A representatives.json 路径",
    ),
    config: Path | None = typer.Option(None, "--config", help="factor_clean.yaml"),
    weighting: str | None = typer.Option(
        None, "--weighting", help="合成方式：equal|ic_weighted"
    ),
    rebalance: int | None = typer.Option(
        None, "--rebalance", help="信号再平衡周期（交易日）"
    ),
    top_n: int | None = typer.Option(None, "--top-n", help="每期买入股票数"),
    bottom_n: int | None = typer.Option(None, "--bottom-n", help="每期卖出股票数"),
    fwd_window: int | None = typer.Option(None, "--fwd-window", help="IC 权重 forward 窗口"),
    ic_lookback: int | None = typer.Option(
        None, "--ic-lookback", help="IC 权重评估窗口（交易日）"
    ),
    capital: float | None = typer.Option(None, "--capital", help="回测初始资金"),
    max_weight: float | None = typer.Option(None, "--max-weight", help="单票最大权重"),
    dead_zone: float | None = typer.Option(None, "--dead-zone", help="换仓死区"),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用因子磁盘缓存"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="输出目录"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """Phase C：代表因子合成信号 + 与单因子对比回测。"""
    try:
        cfg = load_factor_clean_config(config) if config is not None else {}
        weighting = weighting if weighting is not None else str(
            cfg.get("synth_weighting", "equal")
        )
        rebalance = rebalance if rebalance is not None else int(
            cfg.get("synth_rebalance", 20)
        )
        top_n = top_n if top_n is not None else int(cfg.get("synth_top_n", 10))
        bottom_n = bottom_n if bottom_n is not None else int(
            cfg.get("synth_bottom_n", 5)
        )
        fwd_window = fwd_window if fwd_window is not None else int(
            cfg.get("fwd_window", 5)
        )
        ic_lookback = ic_lookback if ic_lookback is not None else int(
            cfg.get("ic_lookback", 60)
        )
        rep_arg: list[str] | Path = (
            Path(representatives)
            if Path(representatives).suffix == ".json"
            else [s.strip() for s in representatives.split(",") if s.strip()]
        )
        out = run_phase_c(
            state_path=state,
            ohlcv_path=data,
            representatives=rep_arg,
            synth_weighting=weighting,
            fwd_window=fwd_window,
            ic_lookback=ic_lookback,
            rebalance=rebalance,
            top_n=top_n,
            bottom_n=bottom_n,
            use_cache=not no_cache,
            output_dir=output_dir,
            capital=capital if capital is not None else 1_000_000,
            max_weight=max_weight if max_weight is not None else 0.3,
            dead_zone=dead_zone if dead_zone is not None else 0.015,
        )
        summary = out["summary"]
        if json_out:
            typer.echo(
                json.dumps(summary, ensure_ascii=False, indent=2, default=str)
            )
            return
        typer.echo(
            f"合成 Sharpe: {summary['synth_sharpe']:.3f}  "
            f"最佳单因子: {summary['best_single']} "
            f"(Sharpe {summary['best_single_sharpe']:.3f})"
        )
        typer.echo(
            f"合成 > 最佳单因子: {'是' if summary['synth_beats_best_single'] else '否'}"
        )
        if output_dir is not None:
            typer.echo(f"输出: {output_dir}")
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc
```

Run: `.venv/bin/python -m pytest tests/cli/test_clean_c_cmd.py -q`
Expected: 2 passed

- [ ] **Step 5: 配置校验测试补绿**

在 `tests/config/` 下找到 `load_factor_clean_config` 既有测试文件（如 `tests/config/test_loader.py`），追加：

```python
def test_load_factor_clean_config_synth_defaults_and_validation(tmp_path):
    import pytest

    from config.loader import load_factor_clean_config

    p = tmp_path / "factor_clean.yaml"
    p.write_text("synth_weighting: ic_weighted\nsynth_top_n: 3\n", encoding="utf-8")
    cfg = load_factor_clean_config(p)
    assert cfg["synth_weighting"] == "ic_weighted"
    assert cfg["synth_rebalance"] == 20  # 缺省合并
    assert cfg["synth_top_n"] == 3
    p.write_text("synth_weighting: bogus\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_factor_clean_config(p)
```

Run: `.venv/bin/python -m pytest tests/config/ -q`
Expected: PASS（新测试绿；若既有测试文件路径不同，按实际文件追加）

- [ ] **Step 6: Commit**

```bash
git add src/analysis/plot.py src/config/loader.py configs/factor_clean.yaml \
        src/yq/factors.py tests/analysis/test_plot.py tests/cli/test_clean_c_cmd.py tests/config/
git commit -m "feat(yq): factor clean-c CLI + Phase C 配置 + 净值对比图"
```

---

### Task 6: 契约文档同步 + 全量回归

**Files:**
- Modify: `docs/data-schemas.md`、`docs/project-plan.md`、`docs/history.md`、`docs/factors-clean.md`

- [ ] **Step 1: data-schemas.md**

在因子清洗相关 schema 段追加：

```markdown
### Phase C 合成信号（factors/ops/synth.py + analysis/factor_synth.py）

- `combine_factor_scores(factor_df, factors, weights=None) -> pd.Series`：
  每日截面 `rank(pct=True)` 归一化 → 带符号权重加权平均（负权重 = 1-rank 反向）→
  综合得分（name="synth_score"）；某行全部因子 NaN → NaN；等权为默认。
- `scores_to_signals(factor_df, score, *, rebalance=20, top_n=10, bottom_n=5) -> DataFrame`：
  列 `(date, code, signal, confidence)`——signal ∈ {1,-1,0}（int）、confidence ∈ [0,1]；
  每 rebalance 日截面得分 top_n 买入 / bottom_n 卖出 / 前持仓退出卖出；得分 NaN 不入选。
- `compute_ic_weights(state, factors, *, as_of, fwd_window=5, lookback=60) -> dict[str, float]`：
  IC 均值权重（带符号），Σ|w|=1；全部无效 → 等权。
- `run_phase_c(...) -> dict`：键 `signals`（合成信号）/ `compare`（回测对比表，
  index=strategy，列 = BacktestEngine metrics）/ `equity_curves` / `summary`
  （synth_weighting / best_single / synth_sharpe / best_single_sharpe /
  synth_beats_best_single）。output_dir 写 synth_signals.parquet /
  backtest_compare.parquet / equity_compare.png / summary.json。
- 合成信号与 `Strategy.generate_signal` 输出格式一致（date, code, signal, confidence），
  可直接喂 `backtest.pipeline.run_pipeline`；Phase C 不改 strategies/portfolio 模块。
```

- [ ] **Step 2: project-plan.md**

把 `| context (因子选择) | 🔲 路线图 |` 行更新为：

```markdown
| context (因子选择) | 🔲 路线图 | Phase C: factors/ops/synth.py（合成得分/信号/IC 权重）+ analysis/factor_synth.py::run_phase_c + yq factor clean-c（合成信号 vs 单因子回测对比） |
```

（若该行不存在，按现有表格行更新为 Phase C 状态。）

- [ ] **Step 3: history.md**

新增 Phase 29 段（仿 Phase 27/28 格式，写在文件末尾 `## Phase 29:` 之后），内容含：动机、合成口径（每日截面 rank + 带符号 IC 权重）、回测公平性约定、Task 1-5 的 commit 摘要、全量回归数字。**Task 6 只写框架（动机 + 设计口径 + commits 预留），Task 7 完成后补结果段。**

- [ ] **Step 4: factors-clean.md**

把 §6 标题行 `## 6. Phase C：合成信号接入策略层` 下的内容标注状态：

```markdown
> **状态：✅ 已实施（2026-08-06）**。实现计划见 [phase-c-synth-plan.md](phase-c-synth-plan.md)，
> 执行记录见 [history.md](history.md) Phase 29。本节保留为设计说明（合成口径/回测对比动机），
> 与实现契约（data-schemas.md）一致。
```

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: **1119 + 新增（11 纯函数 + 5 编排 + 2 CLI + 1 plot + 1 config ≈ 1139）passed, 0 failed**

Run: `.venv/bin/python -m ruff check src/factors/ops/synth.py src/analysis/factor_synth.py src/analysis/plot.py src/config/loader.py src/yq/factors.py tests/factors/test_synth.py tests/analysis/test_factor_synth.py tests/analysis/test_plot.py tests/cli/test_clean_c_cmd.py && .venv/bin/python -m ruff format src/factors/ops/synth.py src/analysis/factor_synth.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add docs/data-schemas.md docs/project-plan.md docs/history.md docs/factors-clean.md
git commit -m "docs: Phase C 契约同步（data-schemas/project-plan/history/factors-clean）"
```

---

### Task 7: 全市场真实验证

**Files:**
- Modify: `docs/history.md`

**输入：**
- state：`data/audit/factor_monitor_full/state.parquet`
- ohlcv：`data/clean/full_market_ohlcv.parquet`（4999 股、近 3 年）
- representatives：`data/audit/factor_clean_a/representatives.json`（Phase A 产物，4 个代表：calc_atr_12d / calc_close_vol_rank_cov_5d / calc_high_vol_rank_corr_3d / calc_vol_rank_intraday_corr_6d）
- 命令：
  `yq factor clean-c --state data/audit/factor_monitor_full/state.parquet --data data/clean/full_market_ohlcv.parquet --representatives data/audit/factor_clean_a/representatives.json --output-dir data/audit/factor_clean_c --json`

- [ ] **Step 1: 真实运行**

Run（前台约 2 分钟超时；若超时用 nohup 后台跑）：
`cd /Users/erwei/.hermes/project/yoyo-quant && mkdir -p data/audit/factor_clean_c && .venv/bin/yq factor clean-c --state data/audit/factor_monitor_full/state.parquet --data data/clean/full_market_ohlcv.parquet --representatives data/audit/factor_clean_a/representatives.json --output-dir data/audit/factor_clean_c --json 2>data/audit/factor_clean_c/stderr.log; echo "exit=$?"`
Expected: exit=0；JSON 输出含 synth_sharpe / best_single / synth_beats_best_single

- [ ] **Step 2: 核对产物**

Run: `ls -la data/audit/factor_clean_c/ && .venv/bin/python -c "
import json, pandas as pd
s = json.load(open('data/audit/factor_clean_c/summary.json'))
print('synth_sharpe =', s['synth_sharpe'])
print('best_single =', s['best_single'], 'sharpe =', s['best_single_sharpe'])
print('synth_beats_best_single =', s['synth_beats_best_single'])
c = pd.read_parquet('data/audit/factor_clean_c/backtest_compare.parquet')
print(c[['total_return','annual_return','sharpe_ratio','max_drawdown','win_rate','trade_count']].to_string())
sig = pd.read_parquet('data/audit/factor_clean_c/synth_signals.parquet')
print('signals:', len(sig), 'rows; signal 分布:', sig['signal'].value_counts().to_dict())
"`
Expected: 4 产物齐全；信号行数与 rebalance/top_n/bottom_n 匹配；对比表可读

- [ ] **Step 3: 结果记录 + 验收**

在 `docs/history.md` Phase 29 段补结果小节（含：命令、窗口/参数、synth_sharpe / best_single / synth_beats_best_single、对比表摘要、结论）。**验收标准**：若合成 Sharpe ≥ 最佳单因子 → 记录"组合优于单因子"；若 < → 如实记录（可能冗余未去干净或合成无效），按计划约定不擅自调参数，记录后问用户。

Run: `.venv/bin/python -m pytest -q`
Expected: 全量回归仍绿

- [ ] **Step 4: Commit**

```bash
git add docs/history.md
git commit -m "docs: Phase C 全市场真实验证结果"
```

---

## Self-Review

**1. Spec coverage（§6 + §9 + §3）：**
- §6 "按等权或 IC 加权合成单一信号" → Task 1（等权 + 带符号权重）+ Task 3（IC 权重）✅
- §6 "输出为 strategies 模块输入格式（date, code, signal, confidence）" → Task 2（scores_to_signals）+ Task 4（信号 DataFrame 契约）✅
- §6 "接入既有 backtest 管道，与单因子最佳对比" → Task 4（compare_backtests 走 run_pipeline，同参数公平对比 + synth_beats_best_single 标志）✅
- §6 "不改变 strategies/portfolio 模块本身，只新增转换层" → 全部 task 不 import strategies/portfolio；信号格式与 Strategy 输出一致即可喂 run_pipeline ✅
- §9 "synth_weighting: equal | ic_weighted 配置化" → Task 5（FACTOR_CLEAN_DEFAULTS + yaml + 校验 + CLI --weighting）✅
- §3.1 "操作能力落 factors/ops/，编排落 analysis" → synth.py（ops）+ factor_synth.py（analysis）✅
- §3.4 目录结构图 "ops/synth.py # Phase C：合成信号（新增）" → Task 1-3 落位 ✅

**2. Placeholder scan：** 无 TBD/“类似 Task N”/“实现细节省略”。每个 task 有完整测试代码 + 最小实现 + 精确命令与预期输出。Task 6 Step 3 的 history 结果段标注"Task 7 后补"是有意的两阶段（结果依赖真实运行），非占位符。

**3. Type consistency：**
- `combine_factor_scores(factor_df, factors, weights=None) -> pd.Series`：Task 1 定义，Task 4/run_phase_c 消费（`weights=weights` 可为 None=等权）✅
- `scores_to_signals(factor_df, score, *, rebalance, top_n, bottom_n) -> DataFrame`：Task 2 定义，Task 4 消费（关键词参数一致）✅
- `compute_ic_weights(state, factors, *, as_of, fwd_window, lookback) -> dict[str, float]`：Task 3 定义，Task 4 消费（fwd_window 来自 config 默认 5、lookback=ic_lookback）✅
- `run_phase_c(...)` 返回 dict 键：Task 4 定义（signals/compare/equity_curves/summary），Task 4 测试与 Task 7 命令断言一致 ✅
- `compare_backtests(signals_map, data, *, capital, max_weight, dead_zone)`：Task 4 定义与测试一致 ✅
- `plot_equity_compare(curves)`：Task 5 Step 1 定义，Task 4 run_phase_c output_dir 分支引用（import 延迟到函数内，Task 5 已交付）✅
- CLI 参数名 ↔ run_phase_c 参数名：--weighting→synth_weighting、--rebalance→rebalance、--top-n→top_n、--bottom-n→bottom_n、--ic-lookback→ic_lookback、--fwd-window→fwd_window ✅

**已知偏差（计划内声明，非缺陷）：**
- `run_phase_c` 的 `exclude_untradable` 未暴露：可交易性过滤由 `run_pipeline` 内部（filter_tradable）执行，合成信号阶段不涉及 forward return，无需该参数（与 Phase B 的 test 期 IC 计算不同）。
- 单因子对比信号与合成信号共用 `scores_to_signals`，因此单因子也是"rank → top_n/bottom_n 轮动"，与合成信号完全同构，保证对比公平（不引入自定义单因子策略）。
