# Phase A：因子相关性分析 + 去冗余 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 按 task 逐个实现；每 task 走完整 TDD 循环（写失败测试 → 跑失败 → 最小实现 → 跑通过 → commit），实现前 invoke `karpathy-guidelines` skill。

**Goal:** 在因子生命周期监控之上新增"相关性去冗余"能力：对 active/decaying 因子计算滚动因子值截面 rank 相关矩阵 → 阈值连边 + 层次聚类 → 每簇留一个代表因子，输出可审计的代表清单与可视化，回答"哪些因子构成真正分散的组合"。

**Architecture:** 纯函数（`factors/ops/correlation.py`）→ 编排（`analysis/factor_clean.py`，只读 monitor 的 state.parquet + 全市场 ohlcv）→ 绘图（`analysis/plot.py` 新增两个函数）→ CLI（`yq factor clean-a`）。因子值一律经 `registry.run_factor`（磁盘缓存），不重写因子计算。

**Tech Stack:** Python 3.11+ / pandas / numpy / scipy.cluster.hierarchy（1.17.1 已装）/ matplotlib（Agg）/ pytest / typer。

---

## Global Constraints

- 环境：一律用 `.venv/bin/python` 与 `.venv/bin/pytest`（系统 python3.14 缺依赖）
- 测试基线：全量 1058 单测 + 30 pipeline；每个 task 合并后全量不得回退
- 项目铁律：绝对 TDD（失败测试先行）、模块解耦（新代码只依赖下文"Interfaces"列出的接口）、禁止生产代码 mock
- 因子值获取：只走 `factors.registry.run_factor`（磁盘缓存 `data/factors/`；测试一律 `use_cache=False` 防污染）
- ruff：只清本 task 引入的问题（`--fix` + 折行），存量 27 处错误不碰
- 不引入新数据源、不改 strategies/portfolio/risk 契约；Phase A 只读 monitor 产物
- 中文 docstring / 报错信息（对齐 evaluation.py 先例）；私有校验函数不跨模块 import（`_require_*` 各自文件内定义）

---

## 影响面与接口速查（已核实）

| 复用 | 位置 | 签名要点 |
|------|------|---------|
| 因子动态发现/取值 | `factors.registry.list_factors` / `run_factor(name, df, *, cache_dir, use_cache, **params) -> pd.Series` | 逐行对齐输入；缺列抛 KeyError |
| monitor 状态长表 | `analysis.factor_monitor.STATE_COLS`（date/factor/fwd_window/ic/rolling_ic/rolling_ir/t_stat/state/sustain_days）、`LOOKBACK_MAX = 60` | state.parquet 长表，`(date, factor, fwd_window)` 唯一键 |
| 配置加载 | `src/config/loader.py` 现有 `load_config` **不可复用**（强校验 strategies/risk）→ Task 6 新增 `load_factor_clean_config` | 见 Task 6 |
| 绘图先例 | `analysis.plot`（`matplotlib.use("Agg")` 在测试文件头设置；`plot_sweep_heatmap`/`plot_factor_health_heatmap` 返回 `plt.Figure`） | 新函数沿用返回 Figure 契约 |
| CLI 先例 | `src/yq/factors.py` `factor_app` 命令组（monitor 命令签名见下）；CLI 测试在 `tests/cli/`（typer `CliRunner`） | 新命令 `clean-a` |

**monitor CLI 现有参数（Task 6 对齐风格）**：`--data`（必填 Path）、`--factor` 可重复、`--windows "5"`、`--window 60`、`--min-sustain 20`、`--min-obs 5`、`--t-active 2.0`、`--t-decay 1.0`、`--full`、`--no-cache`、`--output-dir`、`--json`。

---

## Task 1: `compute_corr_matrix` — 滚动因子值截面相关矩阵

**Files:**
- Create: `src/factors/ops/correlation.py`
- Test: `tests/factors/test_correlation.py`

**Interfaces:**
- Consumes: 无（纯 pandas/numpy；自带 `_require_cols` 校验，不 import evaluation 私有函数）
- Produces: `compute_corr_matrix(factor_df: pd.DataFrame, factors: list[str], *, window: int = 60, method: str = "spearman", agg: str = "mean", min_obs: int = 20) -> pd.DataFrame`

**语义**：`factor_df` 为宽表（含 date/code + 每个 factor 一列，任意行序）。取**最近 `window` 个交易日**；对每对因子，逐日对当日截面（该日全部股票的因子值对）算 spearman 秩相关得到每日 ρ 序列，按 `agg`（mean/median）聚合为标量；对角线恒为 1.0；某日截面有效样本 < `min_obs` 则当日跳过；整段无有效日期的因子对为 NaN。返回对称矩阵，index=columns=factors。

- [ ] **Step 1: 写失败测试**

`tests/factors/test_correlation.py`（含数据构造 helper）：

```python
import numpy as np
import pandas as pd
import pytest

from factors.ops.correlation import compute_corr_matrix


def _make_factor_df(seed=0, n_days=100, n_stocks=40):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    codes = [f"{600000 + i}" for i in range(n_stocks)]
    s = rng.normal(size=n_stocks)   # F1/F2 共享的股票特质分
    t = rng.normal(size=n_stocks)   # F3 独立特质分
    rows = []
    for d in dates:
        for i, c in enumerate(codes):
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "f1": s[i] + rng.normal(scale=0.05),
                    "f2": s[i] + rng.normal(scale=0.05),
                    "f3": t[i] + rng.normal(scale=0.05),
                }
            )
    return pd.DataFrame(rows)


def test_corr_matrix_high_corr_pair():
    df = _make_factor_df()
    mat = compute_corr_matrix(df, ["f1", "f2", "f3"])
    assert mat.loc["f1", "f2"] > 0.9   # 同源 → 每天排序几乎一致
    assert abs(mat.loc["f1", "f3"]) < 0.3  # 独立 → 接近 0


def test_corr_matrix_symmetric_diagonal():
    df = _make_factor_df()
    mat = compute_corr_matrix(df, ["f1", "f2", "f3"])
    assert list(mat.index) == ["f1", "f2", "f3"]
    assert list(mat.columns) == ["f1", "f2", "f3"]
    assert mat.loc["f1", "f2"] == pytest.approx(mat.loc["f2", "f1"])
    assert (np.diag(mat.to_numpy()) == 1.0).all()
    assert mat.values.dtype == np.float64


def test_corr_matrix_window_truncation():
    # 前 80 天 f1 与 f2 同向，后 20 天反向 → 短窗口看到负相关
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2025-06-02", periods=100)
    codes = [f"{600000 + i}" for i in range(20)]
    rows = []
    for i, d in enumerate(dates):
        for j, c in enumerate(codes):
            v = rng.normal(size=1)[0]
            sign = 1.0 if i < 80 else -1.0
            rows.append({"date": d, "code": c, "f1": v, "f2": sign * v + rng.normal(scale=0.05)})
    df = pd.DataFrame(rows)
    short = compute_corr_matrix(df, ["f1", "f2"], window=20)
    full = compute_corr_matrix(df, ["f1", "f2"], window=100)
    assert short.loc["f1", "f2"] < -0.5
    assert full.loc["f1", "f2"] > 0.0


def test_corr_matrix_insufficient_obs_nan():
    df = _make_factor_df(n_stocks=5)  # 每日截面仅 5 个样本
    mat = compute_corr_matrix(df, ["f1", "f2"], min_obs=50)
    assert np.isnan(mat.loc["f1", "f2"])


def test_corr_matrix_missing_column_raises():
    df = _make_factor_df()
    with pytest.raises(ValueError, match="f4"):
        compute_corr_matrix(df, ["f1", "f4"])


def test_corr_matrix_bad_args_raise():
    df = _make_factor_df()
    with pytest.raises(ValueError, match="agg"):
        compute_corr_matrix(df, ["f1", "f2"], agg="max")
    with pytest.raises(ValueError, match="window"):
        compute_corr_matrix(df, ["f1", "f2"], window=0)
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factors.ops.correlation'`

- [ ] **Step 3: 最小实现**

`src/factors/ops/correlation.py`：

```python
"""因子相关性分析（Phase A）：滚动截面 rank 相关矩阵 + 聚类去冗余。

纯函数、无状态，对齐 ``factors.ops.evaluation`` 的契约风格。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _require_cols(df: pd.DataFrame, cols: tuple[str, ...], who: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{who}: 缺少列 {missing}")


def compute_corr_matrix(
    factor_df: pd.DataFrame,
    factors: list[str],
    *,
    window: int = 60,
    method: str = "spearman",
    agg: str = "mean",
    min_obs: int = 20,
) -> pd.DataFrame:
    """计算因子两两的滚动截面秩相关矩阵。

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date`` / ``code`` 与每个因子一列，任意行序。
    factors : list[str]
        参与分析的因子列名。
    window : int
        只取最近 ``window`` 个交易日（按 date 去重排序取尾部）。
    method : str
        相关性方法，透传给 ``Series.corr``，默认 ``spearman``。
    agg : str
        每日相关序列的聚合方式：``mean`` / ``median``。
    min_obs : int
        单日截面有效样本数下限，低于该值的日期跳过。

    Returns
    -------
    DataFrame
        对称矩阵，index=columns=factors；对角线 1.0；数据不足的因子对为 NaN。
    """
    if not isinstance(window, int) or window < 1:
        raise ValueError(f"window 必须为正整数，收到 {window!r}")
    if agg not in {"mean", "median"}:
        raise ValueError(f"agg 必须为 'mean' 或 'median'，收到 {agg!r}")
    cols = ("date", "code") + tuple(factors)
    _require_cols(factor_df, cols, "compute_corr_matrix")

    dates = sorted(factor_df["date"].unique())[-window:]
    sub = factor_df[factor_df["date"].isin(dates)]

    mat = pd.DataFrame(index=factors, columns=factors, dtype=np.float64)
    for i, f1 in enumerate(factors):
        for f2 in factors[i + 1 :]:
            daily: list[float] = []
            for _d, grp in sub.groupby("date"):
                pair = grp[[f1, f2]].dropna()
                if len(pair) < min_obs:
                    continue
                r = pair[f1].corr(pair[f2], method=method)
                if not np.isnan(r):
                    daily.append(float(r))
            if daily:
                val = float(np.mean(daily)) if agg == "mean" else float(np.median(daily))
                mat.loc[f1, f2] = mat.loc[f2, f1] = val
    np.fill_diagonal(mat.to_numpy(), 1.0)
    return mat
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/correlation.py tests/factors/test_correlation.py
git commit -m "feat(factors): 滚动截面秩相关矩阵 compute_corr_matrix（Phase A）"
```

---

## Task 2: `cluster_redundant` — 阈值连边 + 层次聚类

**Files:**
- Modify: `src/factors/ops/correlation.py`（追加函数）
- Modify: `tests/factors/test_correlation.py`（追加用例）

**Interfaces:**
- Consumes: `compute_corr_matrix` 输出（Task 1）
- Produces: `cluster_redundant(corr_matrix: pd.DataFrame, *, threshold: float = 0.7, linkage_method: str = "ward") -> pd.DataFrame`（列：`factor` / `cluster_id`；cluster_id 为 0 起的整数，按因子首次出现顺序编号）

**语义**：距离 d = 1 − |ρ|；`scipy.cluster.hierarchy.linkage(condensed_d, method=linkage_method)` 层次聚类；`fcluster(Z, t=1-threshold, criterion="distance")` 剪枝——阈值语义为"距离空间 1−threshold"（与设计文档 |ρ|>threshold 连边的意图一致，docstring 注明：ward 合并代价非成对 ρ 上限，行为以 TDD 锚点为准）。corr_matrix 含 NaN 时距离填 1.0（视为不相关，不强行合并）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/factors/test_correlation.py`：

```python
from factors.ops.correlation import cluster_redundant


def _corr_of(pairs, factors=("a", "b", "c")):
    # 由 (f1, f2, rho) 列表构造对称矩阵，未给的对为 0
    mat = pd.DataFrame(np.zeros((3, 3)), index=list(factors), columns=list(factors))
    for f1, f2, r in pairs:
        mat.loc[f1, f2] = mat.loc[f2, f1] = r
    np.fill_diagonal(mat.to_numpy(), 1.0)
    return mat


def test_cluster_high_corr_grouped():
    corr = _corr_of([("a", "b", 0.95), ("a", "c", 0.1), ("b", "c", 0.05)])
    out = cluster_redundant(corr, threshold=0.7)
    assert out.loc[out["factor"] == "a", "cluster_id"].iloc[0] == out.loc[
        out["factor"] == "b", "cluster_id"
    ].iloc[0]
    assert out.loc[out["factor"] == "c", "cluster_id"].iloc[0] != out.loc[
        out["factor"] == "a", "cluster_id"
    ].iloc[0]


def test_cluster_all_independent():
    corr = pd.DataFrame(np.eye(3), index=["a", "b", "c"], columns=["a", "b", "c"])
    out = cluster_redundant(corr, threshold=0.7)
    assert out["cluster_id"].nunique() == 3


def test_cluster_threshold_monotonic():
    corr = _corr_of([("a", "b", 0.95)])
    loose = cluster_redundant(corr, threshold=0.7)   # 0.95 > 0.7 → 一簇
    strict = cluster_redundant(corr, threshold=0.98)  # 0.95 < 0.98 → 两簇
    assert loose["cluster_id"].nunique() == 1
    assert strict["cluster_id"].nunique() == 2


def test_cluster_single_factor():
    corr = pd.DataFrame([[1.0]], index=["a"], columns=["a"])
    out = cluster_redundant(corr, threshold=0.7)
    assert out.to_dict("records") == [{"factor": "a", "cluster_id": 0}]


def test_cluster_nan_safe():
    corr = _corr_of([("a", "b", 0.95)])
    corr.loc["a", "c"] = corr.loc["c", "a"] = np.nan
    out = cluster_redundant(corr, threshold=0.7)
    assert len(out) == 3


def test_cluster_invalid_threshold():
    corr = _corr_of([("a", "b", 0.95)])
    with pytest.raises(ValueError, match="threshold"):
        cluster_redundant(corr, threshold=1.5)
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: FAIL — `ImportError: cannot import name 'cluster_redundant'`

- [ ] **Step 3: 最小实现**

追加到 `src/factors/ops/correlation.py`：

```python
def cluster_redundant(
    corr_matrix: pd.DataFrame,
    *,
    threshold: float = 0.7,
    linkage_method: str = "ward",
) -> pd.DataFrame:
    """按相关阈值对因子层次聚类，返回每因子所属簇。

    Parameters
    ----------
    corr_matrix : DataFrame
        ``compute_corr_matrix`` 的对称输出。
    threshold : float
        冗余判定阈值（0 < t < 1）；|ρ| 高于它视为同一信号族。
    linkage_method : str
        scipy linkage 方法，默认 ``ward``。

    Returns
    -------
    DataFrame
        每因子一行：``factor`` / ``cluster_id``（0 起整数，按因子首次出现编号）。

    Notes
    -----
    距离定义为 1 - |ρ|；剪枝阈值为距离空间的 1 - threshold（ward 合并代价
    不等于成对 ρ 上限，簇语义以测试锚点为准）。矩阵中的 NaN 距离按 1.0
    处理（视为不相关）。
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError(f"threshold 必须在 (0, 1) 内，收到 {threshold!r}")
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    factors = list(corr_matrix.index)
    mat = corr_matrix.reindex(index=factors, columns=factors)
    d = (1.0 - mat.abs()).to_numpy(dtype=float)
    d = np.where(np.isnan(d), 1.0, d)
    np.fill_diagonal(d, 0.0)
    if len(factors) == 1:
        return pd.DataFrame({"factor": factors, "cluster_id": [0]})
    Z = linkage(squareform(d, checks=False), method=linkage_method)
    labels = fcluster(Z, t=1.0 - threshold, criterion="distance")  # 1..k
    # 重编号为 0..k-1，按因子首次出现顺序
    seen: dict[int, int] = {}
    ids = []
    for lab in labels:
        if lab not in seen:
            seen[lab] = len(seen)
        ids.append(seen[lab])
    return pd.DataFrame({"factor": factors, "cluster_id": ids})
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: PASS（12 passed，含 Task 1 的 6 个）

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/correlation.py tests/factors/test_correlation.py
git commit -m "feat(factors): 阈值层次聚类 cluster_redundant（Phase A）"
```

---

## Task 3: `select_representative` — 每簇选代表因子

**Files:**
- Modify: `src/factors/ops/correlation.py`（追加函数）
- Modify: `tests/factors/test_correlation.py`（追加用例）

**Interfaces:**
- Consumes: `cluster_redundant` 输出；调用方提供的每因子统计宽表（含 `factor`/`t_stat`/`ir` 列）
- Produces: `select_representative(cluster_df: pd.DataFrame, stats: pd.DataFrame, *, by: str = "t_stat") -> pd.DataFrame`（列：`cluster_id` / `representative` / `members`（list[str]，字典序）/ `member_count`；按 cluster_id 升序）

**语义**：`by` ∈ {"t_stat", "ir", "combined"}；`combined` = (rank(t_stat) + rank(ir)) / 2，rank 升序（越大越好）；NaN 排最后；并列时取因子名字典序小者（确定性）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/factors/test_correlation.py`：

```python
from factors.ops.correlation import select_representative


def _clusters():
    return pd.DataFrame(
        {"factor": ["a", "b", "c", "d"], "cluster_id": [0, 0, 1, 1]}
    )


def _stats():
    return pd.DataFrame(
        {
            "factor": ["a", "b", "c", "d"],
            "t_stat": [1.5, 3.2, 2.1, 0.5],
            "ir": [0.20, 0.40, 0.30, 0.10],
        }
    )


def test_representative_picks_highest_t():
    out = select_representative(_clusters(), _stats(), by="t_stat")
    assert out.loc[out["cluster_id"] == 0, "representative"].iloc[0] == "b"
    assert out.loc[out["cluster_id"] == 1, "representative"].iloc[0] == "c"


def test_representative_by_ir():
    out = select_representative(_clusters(), _stats(), by="ir")
    assert out.loc[out["cluster_id"] == 0, "representative"].iloc[0] == "b"


def test_representative_combined():
    # combined = (rank(t) + rank(ir)) / 2；簇 1 里 c 两维都高于 d
    out = select_representative(_clusters(), _stats(), by="combined")
    assert out.loc[out["cluster_id"] == 1, "representative"].iloc[0] == "c"


def test_representative_members_sorted_and_count():
    out = select_representative(_clusters(), _stats())
    row0 = out.loc[out["cluster_id"] == 0].iloc[0]
    assert row0["members"] == ["a", "b"]
    assert row0["member_count"] == 2


def test_representative_tie_break_lexicographic():
    stats = pd.DataFrame(
        {"factor": ["a", "b"], "t_stat": [2.0, 2.0], "ir": [0.1, 0.1]}
    )
    clusters = pd.DataFrame({"factor": ["a", "b"], "cluster_id": [0, 0]})
    out = select_representative(clusters, stats, by="t_stat")
    assert out.loc[0, "representative"] == "a"


def test_representative_missing_stats_nan_last():
    stats = pd.DataFrame(
        {"factor": ["a", "b"], "t_stat": [2.0, np.nan], "ir": [0.1, 0.2]}
    )
    clusters = pd.DataFrame({"factor": ["a", "b"], "cluster_id": [0, 0]})
    out = select_representative(clusters, stats, by="t_stat")
    assert out.loc[0, "representative"] == "a"


def test_representative_bad_by_raises():
    with pytest.raises(ValueError, match="by"):
        select_representative(_clusters(), _stats(), by="sharpe")
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: FAIL — `ImportError: cannot import name 'select_representative'`

- [ ] **Step 3: 最小实现**

追加到 `src/factors/ops/correlation.py`：

```python
def select_representative(
    cluster_df: pd.DataFrame,
    stats: pd.DataFrame,
    *,
    by: str = "t_stat",
) -> pd.DataFrame:
    """每个簇选一个代表因子（簇内统计值最大者）。

    Parameters
    ----------
    cluster_df : DataFrame
        ``cluster_redundant`` 输出（factor / cluster_id）。
    stats : DataFrame
        每因子统计宽表，须含 ``factor`` 与 ``by`` 所需列（t_stat / ir）。
    by : str
        代表标准：``t_stat`` / ``ir`` / ``combined``（两维 rank 均值）。

    Returns
    -------
    DataFrame
        每簇一行：cluster_id / representative / members（字典序）/ member_count。
    """
    if by not in {"t_stat", "ir", "combined"}:
        raise ValueError(f"by 必须为 t_stat/ir/combined，收到 {by!r}")
    merged = cluster_df.merge(stats, on="factor", how="left")
    if by == "combined":
        if not {"t_stat", "ir"}.issubset(stats.columns):
            raise ValueError("by='combined' 需要 stats 含 t_stat 与 ir 列")
        merged["_score"] = (
            merged["t_stat"].rank(ascending=True, na_option="bottom")
            + merged["ir"].rank(ascending=True, na_option="bottom")
        ) / 2.0
    else:
        if by not in stats.columns:
            raise ValueError(f"stats 缺少列 {by!r}")
        merged["_score"] = merged[by].rank(ascending=True, na_option="bottom")
    # 得分最高者当选；并列时因子名字典序小者优先
    merged = merged.sort_values(["_score", "factor"], ascending=[False, True])
    rows = []
    for cid, grp in merged.groupby("cluster_id", sort=True):
        members = sorted(grp["factor"].tolist())
        rows.append(
            {
                "cluster_id": int(cid),
                "representative": grp["factor"].iloc[0],
                "members": members,
                "member_count": len(members),
            }
        )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/factors/test_correlation.py -v`
Expected: PASS（19 passed）

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/correlation.py tests/factors/test_correlation.py
git commit -m "feat(factors): 簇代表选择 select_representative（Phase A）"
```

---

## Task 4: 绘图 — 相关矩阵热力图 + 聚类树状图

**Files:**
- Modify: `src/analysis/plot.py`（追加两个函数）
- Create: `tests/analysis/test_corr_plot.py`

**Interfaces:**
- Consumes: `compute_corr_matrix` / `cluster_redundant` 的输出（Task 1/2）
- Produces: `plot_corr_matrix(corr_matrix: pd.DataFrame, *, title: str | None = None) -> plt.Figure`；`plot_cluster_dendrogram(corr_matrix: pd.DataFrame, *, threshold: float = 0.7, linkage_method: str = "ward", title: str | None = None) -> plt.Figure`

**语义**：热力图 RdYlGn、vmin=-1/vmax=1（对称、0 居中）、colorbar、x/y 轴标签为因子名（旋转 45°）。树状图用 scipy `dendrogram`（labels=因子名）+ 阈值横线 `axhline(1-threshold)`。两者均返回 `plt.Figure`，沿用 `plot_sweep_heatmap` 先例。

- [ ] **Step 1: 写失败测试**

`tests/analysis/test_corr_plot.py`：

```python
import matplotlib

matplotlib.use("Agg")

import pandas as pd

from analysis.plot import plot_cluster_dendrogram, plot_corr_matrix


def _corr_matrix():
    return pd.DataFrame(
        [
            [1.0, 0.95, 0.10],
            [0.95, 1.0, 0.05],
            [0.10, 0.05, 1.0],
        ],
        index=["a", "b", "c"],
        columns=["a", "b", "c"],
    )


def test_plot_corr_matrix_returns_figure_and_saves(tmp_path):
    fig = plot_corr_matrix(_corr_matrix(), title="test")
    assert fig is not None
    out = tmp_path / "corr.png"
    fig.savefig(out, dpi=72)
    assert out.exists() and out.stat().st_size > 0


def test_plot_corr_matrix_uses_red_yellow_green():
    fig = plot_corr_matrix(_corr_matrix())
    im = fig.axes[0].images[0]
    assert im.get_cmap().name == "RdYlGn"


def test_plot_dendrogram_returns_figure_and_saves(tmp_path):
    fig = plot_cluster_dendrogram(_corr_matrix(), threshold=0.7)
    assert fig is not None
    out = tmp_path / "dendro.png"
    fig.savefig(out, dpi=72)
    assert out.exists() and out.stat().st_size > 0


def test_plot_dendrogram_three_leaves():
    fig = plot_cluster_dendrogram(_corr_matrix())
    leaves = fig.axes[0].get_xticklabels()
    assert len(leaves) == 3
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/analysis/test_corr_plot.py -v`
Expected: FAIL — `ImportError: cannot import name 'plot_corr_matrix'`

- [ ] **Step 3: 最小实现**

追加到 `src/analysis/plot.py`（文件头已有 matplotlib 导入；追加 scipy import 到函数内）：

```python
def plot_corr_matrix(
    corr_matrix: pd.DataFrame,
    *,
    title: str | None = None,
) -> plt.Figure:
    """画因子相关矩阵热力图（RdYlGn，-1..1 对称居中）。

    Parameters
    ----------
    corr_matrix : DataFrame
        ``factors.ops.correlation.compute_corr_matrix`` 的对称输出。
    title : str | None
        图表标题。

    Returns
    -------
    plt.Figure
    """
    fig, ax = plt.subplots(figsize=(max(6, len(corr_matrix) * 0.55), max(6, len(corr_matrix) * 0.55)))
    im = ax.imshow(corr_matrix.to_numpy(dtype=float), cmap="RdYlGn", vmin=-1.0, vmax=1.0)
    fig.colorbar(im, ax=ax, shrink=0.85, label="spearman ρ")
    labels = list(corr_matrix.index)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(labels)), labels, fontsize=9)
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = corr_matrix.to_numpy(dtype=float)[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7)
    ax.set_title(title or "因子相关矩阵（最近窗口）")
    fig.tight_layout()
    return fig


def plot_cluster_dendrogram(
    corr_matrix: pd.DataFrame,
    *,
    threshold: float = 0.7,
    linkage_method: str = "ward",
    title: str | None = None,
) -> plt.Figure:
    """画因子层次聚类树状图，标注冗余判定阈值线。

    Parameters
    ----------
    corr_matrix : DataFrame
        相关矩阵（``compute_corr_matrix`` 输出）。
    threshold : float
        冗余阈值，横线画在距离 1-threshold 处。
    linkage_method : str
        scipy linkage 方法，默认 ``ward``。
    title : str | None
        图表标题。

    Returns
    -------
    plt.Figure
    """
    from scipy.cluster.hierarchy import dendrogram, linkage
    from scipy.spatial.distance import squareform

    factors = list(corr_matrix.index)
    d = (1.0 - corr_matrix.abs()).to_numpy(dtype=float)
    d = np.where(np.isnan(d), 1.0, d)
    np.fill_diagonal(d, 0.0)
    Z = linkage(squareform(d, checks=False), method=linkage_method)
    fig, ax = plt.subplots(figsize=(max(6, len(factors) * 0.6), 4.5))
    dendrogram(Z, labels=factors, ax=ax)
    ax.axhline(1.0 - threshold, color="red", linestyle="--", linewidth=1.0)
    ax.set_ylabel("距离（1 − |ρ|）")
    ax.set_title(title or "因子层次聚类（ward）")
    fig.tight_layout()
    return fig
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/analysis/test_corr_plot.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add src/analysis/plot.py tests/analysis/test_corr_plot.py
git commit -m "feat(analysis): 相关矩阵热力图 + 聚类树状图（Phase A）"
```

---

## Task 5: `run_phase_a` — 编排（state + ohlcv → 代表因子清单）

**Files:**
- Create: `src/analysis/factor_clean.py`
- Create: `tests/analysis/test_factor_clean.py`

**Interfaces:**
- Consumes:
  - `factors.registry.run_factor(name, df, *, cache_dir, use_cache) -> pd.Series`（缺列抛 KeyError）
  - `factors.ops.correlation.compute_corr_matrix / cluster_redundant / select_representative`（Task 1-3）
  - `analysis.factor_monitor.STATE_COLS`、`LOOKBACK_MAX`（=60）
  - 数据：state.parquet（monitor 输出长表）+ ohlcv parquet（date/code/close/...）
- Produces: `run_phase_a(*, state_path: Path, ohlcv_path: Path, corr_window: int = 60, corr_threshold: float = 0.7, cluster_linkage: str = "ward", representative_by: str = "t_stat", fwd_window: int = 5, exclude_untradable: bool = True, cache_dir: Path | None = None, use_cache: bool = True, output_dir: Path | None = None) -> dict`

**返回 dict 键**：`as_of`（pd.Timestamp，最新 state 日期）、`factors`（list[str] 候选）、`skipped`（list[str]）、`corr_matrix`（DataFrame）、`clusters`（DataFrame）、`representatives`（DataFrame）。`output_dir` 给定时写：`corr_matrix.parquet`、`clusters.parquet`、`representatives.json`（含 members 列表）、`corr_heatmap.png`、`dendrogram.png`。

**语义**：
1. 读 state.parquet，取最新日期的 `state ∈ {active, decaying}` 且 `fwd_window == fwd_window` 的因子（排序去重）为候选
2. 读 ohlcv，截取尾部 `corr_window + LOOKBACK_MAX + fwd_window` 个交易日（相关矩阵不需要 forward return，缓冲只保证因子值计算稳定）
3. 逐因子 `run_factor(use_cache=use_cache)`；KeyError → 记入 `skipped` 并跳过
4. `compute_corr_matrix` → `cluster_redundant` → `select_representative`（stats 取自 state 最新日期该因子的 t_stat/ir，fwd_window 匹配）
5. 写 output_dir（若指定），返回 dict

- [ ] **Step 1: 写失败测试**

`tests/analysis/test_factor_clean.py`：

```python
import json

import numpy as np
import pandas as pd
import pytest

from analysis.factor_clean import run_phase_a
from analysis.factor_monitor import STATE_COLS


def _ohlcv(n_days=120, n_stocks=40, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    codes = [f"{600000 + i}" for i in range(n_stocks)]
    rows = []
    for d in dates:
        for c in codes:
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "open": close - 0.05,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False,
                    "limit_down": False,
                    "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _state(as_of="2025-12-01"):
    rows = [
        ("2025-12-01", "calc_momentum_5d_change", 5, 0.05, 0.06, 0.8, 4.5, "active", 100),
        ("2025-12-01", "calc_volume_ratio", 5, 0.04, 0.05, 0.7, 3.9, "active", 95),
        ("2025-12-01", "calc_hv", 5, -0.02, -0.03, -0.4, -2.1, "dead", 30),
        ("2025-12-01", "calc_earnings_surprise", 5, np.nan, np.nan, np.nan, np.nan, "active", 0),
    ]
    return pd.DataFrame(rows, columns=STATE_COLS)


def test_run_phase_a_filters_active_decaying(tmp_path):
    state_path = tmp_path / "state.parquet"
    ohlcv_path = tmp_path / "ohlcv.parquet"
    _state().to_parquet(state_path, index=False)
    _ohlcv().to_parquet(ohlcv_path, index=False)

    out = run_phase_a(
        state_path=state_path,
        ohlcv_path=ohlcv_path,
        use_cache=False,
    )
    assert set(out["factors"]) == {"calc_momentum_5d_change", "calc_volume_ratio"}
    assert len(out["skipped"]) == 1 and "calc_earnings_surprise" in out["skipped"][0]  # 缺 earnings 列
    assert out["corr_matrix"].shape == (2, 2)
    assert out["corr_matrix"].index.tolist() == ["calc_momentum_5d_change", "calc_volume_ratio"]
    assert out["clusters"].columns.tolist() == ["factor", "cluster_id"]
    assert out["representatives"].columns.tolist() == [
        "cluster_id",
        "representative",
        "members",
        "member_count",
    ]
    assert out["representatives"]["member_count"].sum() == 2
    assert out["as_of"] == pd.Timestamp("2025-12-01")


def test_run_phase_a_writes_outputs(tmp_path):
    state_path = tmp_path / "state.parquet"
    ohlcv_path = tmp_path / "ohlcv.parquet"
    out_dir = tmp_path / "out"
    _state().to_parquet(state_path, index=False)
    _ohlcv().to_parquet(ohlcv_path, index=False)

    out = run_phase_a(
        state_path=state_path,
        ohlcv_path=ohlcv_path,
        use_cache=False,
        output_dir=out_dir,
    )
    assert (out_dir / "corr_matrix.parquet").exists()
    assert (out_dir / "clusters.parquet").exists()
    assert (out_dir / "representatives.json").exists()
    assert (out_dir / "corr_heatmap.png").exists()
    assert (out_dir / "dendrogram.png").exists()
    payload = json.loads((out_dir / "representatives.json").read_text())
    assert payload["as_of"] == "2025-12-01"
    assert len(payload["representatives"]) == out["representatives"]["member_count"].sum()


def test_run_phase_a_missing_state_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_phase_a(state_path=tmp_path / "nope.parquet", ohlcv_path=tmp_path / "nope.parquet")
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/analysis/test_factor_clean.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.factor_clean'`

- [ ] **Step 3: 最小实现**

`src/analysis/factor_clean.py`：

```python
"""因子清洗编排（Phase A/B/C 业务层）。

Phase A：读 monitor 的 state 长表 + 全市场 ohlcv → 候选因子 → 相关矩阵 →
聚类 → 代表因子清单。只读 monitor 产物，不重算 IC/状态。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.factor_monitor import LOOKBACK_MAX, STATE_COLS
from factors.ops.correlation import (
    cluster_redundant,
    compute_corr_matrix,
    select_representative,
)
from factors.registry import run_factor

ACTIVE_STATES = ("active", "decaying")


def _load_state(state_path: Path) -> pd.DataFrame:
    path = Path(state_path)
    if not path.exists():
        raise FileNotFoundError(f"state 文件不存在: {path}")
    df = pd.read_parquet(path)
    if not set(STATE_COLS).issubset(df.columns):
        raise ValueError(f"state.parquet 缺少列，需要 {STATE_COLS}")
    return df


def run_phase_a(
    *,
    state_path: Path,
    ohlcv_path: Path,
    corr_window: int = 60,
    corr_threshold: float = 0.7,
    cluster_linkage: str = "ward",
    representative_by: str = "t_stat",
    fwd_window: int = 5,
    exclude_untradable: bool = True,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    output_dir: Path | None = None,
) -> dict:
    """Phase A 编排：候选因子 → 相关矩阵 → 聚类 → 代表因子清单。

    Parameters
    ----------
    state_path : Path
        monitor 输出的 state.parquet（STATE_COLS 长表）。
    ohlcv_path : Path
        全市场行情 parquet（date/code/close/...）。
    corr_window / corr_threshold / cluster_linkage / representative_by
        透传给 correlation 纯函数（见 ``factors/ops/correlation``）。
    fwd_window : int
        取 state 中该 forward 窗口的统计行。
    exclude_untradable : bool
        预留：与 monitor 语义一致（当前 Phase A 只用因子值，无 forward return）。
    cache_dir / use_cache
        透传给 ``run_factor``。
    output_dir : Path | None
        给定时写 corr_matrix/clusters/representatives/PNG。

    Returns
    -------
    dict
        键：as_of / factors / skipped / corr_matrix / clusters / representatives。
    """
    state = _load_state(state_path)
    as_of = state["date"].max()
    mask = (
        (state["date"] == as_of)
        & (state["state"].isin(ACTIVE_STATES))
        & (state["fwd_window"] == fwd_window)
    )
    factors = sorted(state.loc[mask, "factor"].unique().tolist())

    price = pd.read_parquet(ohlcv_path)
    dates = sorted(price["date"].unique())
    cut = max(0, len(dates) - (corr_window + LOOKBACK_MAX + fwd_window))
    tail = price[price["date"] >= dates[cut]]

    values: dict[str, pd.Series] = {}
    skipped: list[str] = []
    for factor in factors:
        try:
            values[factor] = run_factor(
                factor, tail, cache_dir=cache_dir, use_cache=use_cache
            )
        except KeyError as exc:
            skipped.append(f"{factor}（缺列 {exc}）")
            continue

    keep = [f for f in factors if f in values]
    factor_df = tail.assign(**{f: values[f].to_numpy() for f in keep})

    corr = compute_corr_matrix(factor_df, keep, window=corr_window)
    clusters = cluster_redundant(corr, threshold=corr_threshold, linkage_method=cluster_linkage)
    latest = state[(state["date"] == as_of) & (state["fwd_window"] == fwd_window)]
    stats = latest[["factor", "t_stat", "ir"]].drop_duplicates("factor")
    representatives = select_representative(clusters, stats, by=representative_by)

    result = {
        "as_of": as_of,
        "factors": keep,
        "skipped": skipped,
        "corr_matrix": corr,
        "clusters": clusters,
        "representatives": representatives,
    }
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        corr.to_parquet(out / "corr_matrix.parquet", index=True)
        clusters.to_parquet(out / "clusters.parquet", index=False)
        payload = {
            "as_of": str(as_of.date()),
            "corr_threshold": corr_threshold,
            "representative_by": representative_by,
            "representatives": representatives.to_dict("records"),
            "skipped": skipped,
        }
        (out / "representatives.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        from analysis.plot import plot_cluster_dendrogram, plot_corr_matrix

        plot_corr_matrix(corr).savefig(out / "corr_heatmap.png", dpi=110, bbox_inches="tight")
        plot_cluster_dendrogram(corr, threshold=corr_threshold).savefig(
            out / "dendrogram.png", dpi=110, bbox_inches="tight"
        )
    return result
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/analysis/test_factor_clean.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/analysis/factor_clean.py tests/analysis/test_factor_clean.py
git commit -m "feat(analysis): Phase A 编排 run_phase_a（state+ohlcv → 代表因子）"
```

---

## Task 6: CLI `yq factor clean-a` + `configs/factor_clean.yaml`

**Files:**
- Modify: `src/config/loader.py`（追加 `load_factor_clean_config` + `FACTOR_CLEAN_DEFAULTS`）
- Create: `configs/factor_clean.yaml`
- Modify: `src/yq/factors.py`（factor_app 追加 `clean-a` 命令）
- Create: `tests/cli/test_clean_a_cmd.py`
- Modify: `tests/config/test_loader.py`（追加用例）

**Interfaces:**
- Consumes: `run_phase_a`（Task 5）、`load_factor_clean_config`
- Produces: `load_factor_clean_config(path: Path) -> dict`（校验 + 默认值合并，默认见 `FACTOR_CLEAN_DEFAULTS`）；CLI 命令 `yq factor clean-a`（参数 `--state`（必填）、`--data`（必填）、`--config`、`--window 60`、`--threshold 0.7`、`--linkage ward`、`--by t_stat`、`--fwd-window 5`、`--no-cache`、`--output-dir`、`--json`）

**CLI 输出**：非 json 时打印摘要——`as_of`、候选因子数、簇数、每簇代表与成员、skipped；`--json` 输出 `{"as_of", "factors", "skipped", "clusters": [[cid, rep, members]], "outputs": {...}}`。

- [ ] **Step 1: 写失败测试**

`tests/config/test_loader.py` 追加：

```python
from config.loader import FACTOR_CLEAN_DEFAULTS, load_factor_clean_config


def test_load_factor_clean_config_defaults(tmp_path):
    p = tmp_path / "fc.yaml"
    p.write_text("corr_threshold: 0.8\n", encoding="utf-8")
    cfg = load_factor_clean_config(p)
    assert cfg["corr_threshold"] == 0.8
    assert cfg["corr_window"] == FACTOR_CLEAN_DEFAULTS["corr_window"] == 60


def test_load_factor_clean_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_factor_clean_config(tmp_path / "nope.yaml")


def test_load_factor_clean_config_bad_value_raises(tmp_path):
    p = tmp_path / "fc.yaml"
    p.write_text("corr_threshold: 2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="corr_threshold"):
        load_factor_clean_config(p)
```

`tests/cli/test_clean_a_cmd.py`：

```python
import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from analysis.factor_monitor import STATE_COLS
from yq.cli import app

runner = CliRunner()


def _ohlcv(n_days=120, n_stocks=40, seed=0):
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
    rows = [
        ("2025-12-01", "calc_momentum_5d_change", 5, 0.05, 0.06, 0.8, 4.5, "active", 100),
        ("2025-12-01", "calc_volume_ratio", 5, 0.04, 0.05, 0.7, 3.9, "active", 95),
    ]
    p = tmp_path / "state.parquet"
    pd.DataFrame(rows, columns=STATE_COLS).to_parquet(p, index=False)
    return p


def test_clean_a_cmd_runs(tmp_path):
    state = _state(tmp_path)
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["factor", "clean-a", "--state", str(state), "--data", str(data),
         "--no-cache", "--output-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "代表因子" in result.output
    assert (out / "corr_heatmap.png").exists()


def test_clean_a_cmd_json(tmp_path):
    state = _state(tmp_path)
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    result = runner.invoke(
        app,
        ["factor", "clean-a", "--state", str(state), "--data", str(data),
         "--no-cache", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["as_of"] == "2025-12-01"
    assert len(payload["factors"]) == 2


def test_clean_a_cmd_requires_state(tmp_path):
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    result = runner.invoke(app, ["factor", "clean-a", "--data", str(data)])
    assert result.exit_code != 0
```

- [ ] **Step 2: 跑失败**

Run: `.venv/bin/pytest tests/config/test_loader.py tests/cli/test_clean_a_cmd.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_factor_clean_config'` / `No such command 'clean-a'`

- [ ] **Step 3: 最小实现**

`src/config/loader.py` 追加：

```python
FACTOR_CLEAN_DEFAULTS: dict = {
    "corr_threshold": 0.7,
    "corr_window": 60,
    "cluster_linkage": "ward",
    "representative_by": "t_stat",
    "fwd_window": 5,
    "exclude_untradable": True,
}


def load_factor_clean_config(path: Path) -> dict:
    """加载 Phase A/B/C 清洗配置：缺省合并 + 校验。

    ``configs/factor_clean.yaml`` 顶层键即参数名；缺省值见
    ``FACTOR_CLEAN_DEFAULTS``。与 ``load_config`` 不同：不要求
    strategies/risk 段（factor_clean.yaml 是独立清洗配置）。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        user = yaml.safe_load(f) or {}
    cfg = {**FACTOR_CLEAN_DEFAULTS, **user}
    if not 0.0 < float(cfg["corr_threshold"]) < 1.0:
        raise ValueError(f"corr_threshold 必须在 (0,1) 内，收到 {cfg['corr_threshold']!r}")
    if not isinstance(cfg["corr_window"], int) or cfg["corr_window"] < 1:
        raise ValueError(f"corr_window 必须为正整数，收到 {cfg['corr_window']!r}")
    if cfg["cluster_linkage"] not in {"ward", "complete", "average", "single"}:
        raise ValueError(f"cluster_linkage 非法: {cfg['cluster_linkage']!r}")
    if cfg["representative_by"] not in {"t_stat", "ir", "combined"}:
        raise ValueError(f"representative_by 非法: {cfg['representative_by']!r}")
    return cfg
```

`configs/factor_clean.yaml`：

```yaml
# Phase A/B/C 因子清洗配置（load_factor_clean_config 加载，缺省合并）
corr_threshold: 0.7        # 去冗余相关阈值（调低更激进，保留因子更少）
corr_window: 60            # 相关滚动窗口（交易日，与 monitor 一致）
cluster_linkage: ward      # 层次聚类连接方式
representative_by: t_stat  # 簇代表选择标准：t_stat | ir | combined
fwd_window: 5              # 取 state 中该 forward 窗口的统计行
exclude_untradable: true   # 沿用监控默认：排除涨跌停/停牌日
```

`src/yq/factors.py` 追加（import `load_factor_clean_config`、`run_phase_a`；`clean-a` 命令插在 `factor_monitor` 之后）：

```python
@factor_app.command("clean-a")
def factor_clean_a(
    state: Path = typer.Option(..., "--state", help="monitor 输出的 state.parquet"),
    data: Path = typer.Option(..., "--data", help="全市场行情 parquet"),
    config: Path | None = typer.Option(None, "--config", help="factor_clean.yaml"),
    window: int | None = typer.Option(None, "--window", help="相关滚动窗口（交易日）"),
    threshold: float | None = typer.Option(None, "--threshold", help="冗余判定阈值 |ρ|"),
    linkage: str | None = typer.Option(None, "--linkage", help="层次聚类连接方式"),
    by: str | None = typer.Option(None, "--by", help="代表标准：t_stat|ir|combined"),
    fwd_window: int | None = typer.Option(None, "--fwd-window", help="state 的 forward 窗口"),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用因子磁盘缓存"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="输出目录"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """Phase A：因子相关性去冗余（state + ohlcv → 代表因子清单）。"""
    # 优先级：CLI 显式参数 > config 文件 > 内置默认（FACTOR_CLEAN_DEFAULTS）
    cfg = load_factor_clean_config(config) if config is not None else {}
    window = window if window is not None else int(cfg.get("corr_window", 60))
    threshold = threshold if threshold is not None else float(cfg.get("corr_threshold", 0.7))
    linkage = linkage if linkage is not None else str(cfg.get("cluster_linkage", "ward"))
    by = by if by is not None else str(cfg.get("representative_by", "t_stat"))
    fwd_window = fwd_window if fwd_window is not None else int(cfg.get("fwd_window", 5))
    out = run_phase_a(
        state_path=state,
        ohlcv_path=data,
        corr_window=window,
        corr_threshold=threshold,
        cluster_linkage=linkage,
        representative_by=by,
        fwd_window=fwd_window,
        use_cache=not no_cache,
        output_dir=output_dir,
    )
    reps = out["representatives"]
    summary = [
        {
            "cluster_id": int(r["cluster_id"]),
            "representative": r["representative"],
            "members": list(r["members"]),
        }
        for r in reps.to_dict("records")
    ]
    if json_out:
        import json as _json

        typer.echo(
            _json.dumps(
                {
                    "as_of": str(out["as_of"].date()),
                    "factors": out["factors"],
                    "skipped": out["skipped"],
                    "clusters": summary,
                    "outputs": str(output_dir) if output_dir else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo(f"as_of: {out['as_of'].date()}  候选因子: {len(out['factors'])}  簇数: {len(reps)}")
    for r in summary:
        typer.echo(f"  簇 {r['cluster_id']}: 代表因子 {r['representative']}（成员 {r['members']}）")
    if out["skipped"]:
        typer.echo(f"跳过（缺列）: {out['skipped']}", err=True)
    if output_dir is not None:
        typer.echo(f"输出: {output_dir}")
```

- [ ] **Step 4: 跑通过**

Run: `.venv/bin/pytest tests/config/test_loader.py tests/cli/test_clean_a_cmd.py -v`
Expected: PASS（原有用例 + 新 6 个）

- [ ] **Step 5: Commit**

```bash
git add src/config/loader.py configs/factor_clean.yaml src/yq/factors.py tests/config/test_loader.py tests/cli/test_clean_a_cmd.py
git commit -m "feat(yq): factor clean-a CLI + factor_clean.yaml 配置（Phase A）"
```

---

## Task 7: 文档契约 + 全量回归

**Files:**
- Modify: `docs/data-schemas.md`（新增 Phase A 小节）
- Modify: `docs/project-plan.md`（状态表 + 目录树补 correlation.py / factor_clean.py）
- Modify: `docs/history.md`（追加 Phase 27）
- Modify: `docs/factors-clean.md`（§4 状态改为"已实施"，指向实现计划）

**Interfaces:** 无新代码；纯文档 + 回归。

- [ ] **Step 1: 更新 data-schemas.md**

在 `## 行业中性化` 节之后、文件尾部追加：

```markdown
## Phase A 因子相关性去冗余 — factors.ops.correlation 模块

> 纯函数、无状态；输入宽表（date/code/因子列）或相关矩阵；不依赖交易管线。

| 函数 | 输出 | 说明 |
|------|------|------|
| `compute_corr_matrix(factor_df, factors, *, window=60, method="spearman", agg="mean", min_obs=20)` | DataFrame（对称，index=columns=factors） | 取最近 window 个交易日，逐日截面 spearman 相关后按 agg 聚合；对角 1.0，数据不足 NaN |
| `cluster_redundant(corr_matrix, *, threshold=0.7, linkage_method="ward")` | DataFrame（factor/cluster_id） | 距离=1-|ρ|，scipy ward 层次聚类，距离空间阈值 1-threshold 剪枝；NaN 按 1.0 |
| `select_representative(cluster_df, stats, *, by="t_stat")` | DataFrame（cluster_id/representative/members/member_count） | 每簇取 t_stat/ir/combined（rank 均值）最大者；并列取字典序小者 |

### Phase A 编排 — analysis.factor_clean.run_phase_a

- 输入：state.parquet（monitor 长表）+ 全市场 ohlcv parquet
- 候选：最新日期 state ∈ {active, decaying} 且 fwd_window 匹配的因子；run_factor KeyError（缺列）→ skipped
- 输出 dict：as_of / factors / skipped / corr_matrix / clusters / representatives；output_dir 写 parquet + JSON + PNG
- 配置：`configs/factor_clean.yaml`（load_factor_clean_config，默认 corr_threshold=0.7 / corr_window=60 / cluster_linkage=ward / representative_by=t_stat）
- CLI：`yq factor clean-a --state ... --data ... [--window 60] [--threshold 0.7] [--linkage ward] [--by t_stat] [--fwd-window 5] [--no-cache] [--output-dir] [--json]`
```

- [ ] **Step 2: 更新 project-plan.md**

状态表 factors 行附近追加：

```markdown
| factors (相关性去冗余) | ✅ 完成 | Phase A: ops/correlation.py（相关矩阵+聚类+代表）+ analysis/factor_clean.py 编排 + yq factor clean-a + factor_clean.yaml |
```

目录树 `ops/` 块补一行：

```markdown
│   ├── correlation.py        # Phase A: 截面相关矩阵 + 聚类去冗余
```

- [ ] **Step 3: 更新 history.md**

追加 Phase 27 章节（记录：动机=全量首跑 8 个 active 全为量价相关类；决策=因子值截面 rank 相关主口径/IC 时序相关辅助、60 日窗口、active/decaying 候选、|ρ|>0.7 冗余、连通分量语义落在 scipy ward+distance 剪枝；兼容=load_config 强校验故新增 load_factor_clean_config；TDD 全绿 + 全量回归数字）。

- [ ] **Step 4: 全量回归 + ruff**

Run: `.venv/bin/pytest -q 2>&1 | tail -1 && .venv/bin/pytest tests_pipeline/ -q 2>&1 | tail -1`
Expected: 全量 ≥ 1066 passed（基线 1058 + 新 8 个）且 pipeline 30 passed

Run: `.venv/bin/ruff check src/factors/ops/correlation.py src/analysis/factor_clean.py src/analysis/plot.py src/config/loader.py src/yq/factors.py tests/factors/test_correlation.py tests/analysis/test_corr_plot.py tests/analysis/test_factor_clean.py tests/cli/test_clean_a_cmd.py`
Expected: 本任务文件 All checks passed（存量 27 处不在这些文件内则不动）

- [ ] **Step 5: Commit**

```bash
git add docs/data-schemas.md docs/project-plan.md docs/history.md docs/factors-clean.md
git commit -m "docs: Phase A 契约同步（data-schemas/project-plan/history）"
```

---

## Task 8: 全市场真实验证

**Files:** 无新代码；只跑命令 + 记录结果。

- [ ] **Step 1: 跑全市场 Phase A**

Run:
```bash
.venv/bin/yq factor clean-a \
  --state data/audit/factor_monitor_full/state.parquet \
  --data data/clean/full_market_ohlcv.parquet \
  --output-dir data/audit/factor_clean_a \
  --json 2> data/audit/factor_clean_a/stderr.log
```
Expected: exit 0；JSON 含 clusters 列表；stderr 提示 skipped（若有缺列因子）

- [ ] **Step 2: 验证收敛目标**

Run:
```bash
.venv/bin/python - <<'PY'
import json
p = json.load(open("data/audit/factor_clean_a/representatives.json"))
reps = [r["representative"] for r in p["representatives"]]
print("代表因子数:", len(reps))
print("代表:", reps)
# 期望：4 个 GTJA 量价相关类（gtja_99/32/90/1）收敛到 ≤2 个代表
PY
```
Expected: 代表因子数 ≤ 候选因子数；若上一轮 monitor 的 active 集（gtja_99/32/90/1 等）仍在，则收敛到 ≤2 个同族代表（附簇成员表人工核验）

- [ ] **Step 3: 核验可视化**

检查 `data/audit/factor_clean_a/corr_heatmap.png` 与 `dendrogram.png` 已生成、非空；目视"量价相关类"聚成一簇。

- [ ] **Step 4: 记录结果到 history.md**

在 Phase 27 追加小节：命令、代表因子数、收敛情况、skipped 列表、PNG 路径。若实际聚类结果偏离设计预期（如所有候选并成一簇或全散开），**不擅自调阈值**——记录观察并问用户是否调整 `configs/factor_clean.yaml` 的 `corr_threshold`。

- [ ] **Step 5: Commit**

```bash
git add docs/history.md
git commit -m "docs: Phase A 全市场验证结果记录"
```

---

## Self-Review（写计划时已执行）

**1. Spec 覆盖**（对照 `docs/factors-clean.md` §4 与 §9）：
- §4.1 双口径：因子值截面 rank 相关（主）→ Task 1；IC 时序相关 → 本轮未实现，作为 §4.1 表内"辅助诊断"留到需要时加（设计文档未要求首版必须出图，YAGNI，计划无对应 task——见下方"已知取舍"）
- §4.2 窗口/对象/阈值：60 日窗口（Task 1）、active/decaying 候选（Task 5）、|ρ|>0.7（Task 2/6 默认）✓
- §4.3 算法：阈值连边+ward 聚类（Task 2，剪枝语义以测试锚点固化）、每簇代表（Task 3，by 可配）、输出归属簇（representatives.members 可审计）✓
- §4.4 产出：热力图（Task 4）、树状图（Task 4）、代表清单 JSON（Task 5/6）✓；验收"4 个 GTJA 类收敛 ≤2 代表"→ Task 8
- §9 配置项：corr_threshold/corr_window/cluster_linkage/representative_by → configs/factor_clean.yaml（Task 6）✓

**2. 占位符扫描**：所有 step 含完整代码与预期输出；无 TODO/TBD。

**3. 类型一致性**：Task 5 消费 Task 1-3 的精确签名；Task 6 消费 Task 5 的 `run_phase_a` 关键字参数；`STATE_COLS`/`LOOKBACK_MAX` 从 monitor 实读；`load_factor_clean_config` 与 `load_config` 并列不冲突（config/loader.py 已有 `import yaml`，测试文件 import 路径 `from src.config.loader import ...`——若既有测试用相对项目根路径 `src.config.loader`，保持同风格；若为 `from config.loader import`，Task 6 Step 1 里改为同风格）。

**已知取舍（计划内显式记录，不猜用户意图）**：
- 剪枝语义：ward 的 distance 剪枝阈值是距离空间值（1-threshold），非成对 ρ 上限；行为由 TDD 锚点固化，真实数据 Task 8 验证，偏离时问用户
- `exclude_untradable` 参数在 Phase A 只透传不生效（Phase A 无 forward return；该参数为 Phase B/C 预留与 CLI 对齐），docstring 已注明
- IC 时序相关诊断图未纳入本计划（YAGNI；设计文档列为"辅助"），如用户需要可后续追加

---

*计划 v1，2026-08-06。前置：Phase 0 分层重构已完成（docs/factor-clean-plan.md）。执行方式见会话回复中的二选一。*
