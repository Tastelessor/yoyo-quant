# 因子挖掘 Phase 1：分层验证基础设施 + moneyflow 资金流族实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地分层验证基础设施（size × liquidity 两维 9 层）与第一个另类数据因子族——moneyflow 资金流族，跑通"数据源 → 因子 → 全市场+分层 IC 验证 → 适用域标签"的最小闭环，作为后续因子族（情绪/预期差/事件）的样板。

**Architecture:** 纯函数落 `factors/ops/`（层标签 `layering.py` + 分层 IC 扩展 `evaluation.py`），数据管线落 `data/moneyflow.py`（仿 `data/earnings.py`：fetch + PIT 清洗 + 面板化 + parquet 缓存），因子实现落 `factors/mining/sources/moneyflow.py`（注册进 `registry._register_defaults`，与 builtin 因子同机制、被 `list_factors()` 动态发现），评估编排落 `factors/mining/pipeline.py::run_mining_screen`（最小版：因子值 → 层标签对齐 → 全市场 + 9 层 IC/t → 适用域判定）。三层解耦不变：factors/data/analysis 互不 import，靠 DataFrame 与 parquet 交互。

**Tech Stack:** Python 3.11+ / pandas / numpy / tushare（`moneyflow` + `daily_basic` 接口）/ typer / pytest / ruff

## Global Constraints

- **项目铁律**：绝对 TDD（失败测试先行）；模块解耦（通过接口交互，不依赖实现细节）；禁止生产代码 mock；中文 docstring
- **环境**：`.venv/bin/python -m pytest`（`.venv/bin/pytest` shebang 陈旧）；`.venv/bin/python -m ruff`；全量回归基线 **1142 passed**（Phase C 后实测）
- **commit 风格**：`feat(data):` / `feat(factors):` / `feat(yq):` / `docs:`，每个 task 独立 commit
- **分层口径**（设计文档 §3.4，用户确认）：每日截面按 `circ_mv` / `turnover_rate` **三分位**（tercile）→ size ∈ {small, mid, large}、liq ∈ {low, mid, high}，正交 9 层；截面**相对分位**不用绝对阈值；维度事前定死、全层报告、禁止事后挑层
- **tushare 事实**（已核实）：`moneyflow` 单次最大 6000 行、2000 积分门槛，金额单位**万元**，`net_mf_amount` 为官方净流入（基于 L2 主动买卖单，不可简单由大小单相加）；`daily_basic` 的 `circ_mv` 流通市值（**万元**）、`turnover_rate` 换手率（%），单次最大 6000 行；用户积分 15000 分覆盖两者
- **复用既有接口**（不得新建依赖面）：`factors/registry.py`（`run_factor` / `register_factor` / `list_factors` / `_register_defaults`）、`factors/ops/evaluation.py`（`compute_ic` / `compute_forward_returns` / `compute_ir` / `compute_rolling_tstat`）、`data/fetcher.py::fetch_fundamentals`（daily_basic，本计划扩展）、`config/loader.py`（`FACTOR_CLEAN_DEFAULTS` / `load_factor_clean_config`）
- **不耦合** strategies / portfolio / risk；第一阶段不做 monitor 接入（资金流因子进 monitor 需 monitor 的 price_df 含资金流列，属后续编排，本计划只产出"适用域标签评估表"）
- **数据单位**：`fetch_fundamentals` 的 `total_mv` 既有逻辑转**亿元**（`/10000`）；本计划扩展的 `circ_mv` 同步转亿元（与既有列一致）；`moneyflow` 金额保持**万元**；因子比率（净流入/流通市值）为同单位相除，不受单位影响
- **内存**：全市场 ohlcv（55MB）+ daily_basic + moneyflow 面板（近 2 年 ≈ 250 万行 × 20+ 列 ≈ 数百 MB 峰值）全量读 OK；禁止全因子宽表（只保留需要列）

---

## Scope & Future Work（后续阶段路线图，本计划不实现）

**本计划范围**：只做分层验证基础设施（Task 1-3）与 moneyflow 资金流族闭环（Task 4-7）。以下接口与阶段**留到以后**，按 design doc `docs/factor-data-sourcing-plan.md`（v2）§2.6 优先级与 §3.2 因子族划分，供将来写后续实现计划时直接参考（**本计划不实现，不列测试**）：

| 后续阶段 | 数据源（tushare 接口） | 预计落点 | 依赖与待确认（design doc §5） |
|----------|------------------------|----------|------------------------------|
| Phase 2 情绪/游资族（风格核心） | `limit_list_ths` / `limit_list_d` / `limit_step` / `limit_cpt_list`（涨跌停系列）、`top_list` / `top_inst`（龙虎榜） | `data/limit_market.py` + `factors/mining/sources/sentiment.py`（连板高度/炸板率/机构净买入/游资席位） | 接口字段需按 tushare 官方文档核实（doc_id 298/106/107/355/356/357）；小盘高换手层预期强，正是分层验证要救的品种 |
| Phase 3 预期差族 | `report_rc`（卖方一致预期）+ 既有 `forecast`/`express`（`data/earnings.py` 管线扩展 report_rc 锚点） | `data/report_rc.py` + `factors/mining/sources/expectations.py`（surprise/revision/评级分布） | **§5.2 待确认**：`report_rc` 字段与更新频率（逐日 vs 逐报告期）；分析师覆盖偏大中盘 → 预期 universal/大盘层因子 |
| Phase 4 事件族 | `share_float`（解禁）、`stk_holdertrade`（增减持）、`block_trade`（大宗）、`repurchase`（回购） | `data/events_*.py` + `factors/mining/sources/events.py`（解禁压力/增减持/大宗折价/回购） | 事件日稀疏 → 日频面板化（事件日赋值 + 前向填充）；解禁对小盘影响最大，天然条件因子 |
| Phase 5 筹码族 | `stk_holdernumber`（股东人数）、`cyq_chips` / `cyq_perf`（筹码分布） | `data/holdernumber.py` + `factors/mining/sources/chips.py`（股东户数环比/获利盘/成本集中度） | **§5.5 待确认**：`cyq_chips` 先拉样本验证覆盖与数据质量再定接入；季频转日频 |
| Phase 6 挖掘流水线完整版 | —（无新数据源） | `factors/ops/orthogonalize.py`（关卡 4 正交化增量）+ `factors/mining/quality.py`（关卡 1 数据质量）+ `mining/pipeline.py` 扩展（关卡 3 复用 `correlation.py` + `stk_factor` 基准；关卡 5 monitor 接入） | **YAGNI 前置**：先跑通关卡 2 分层验证 + Phase B OOS，确认仍漏"低相关但共线噪声"再实现关卡 4；`stk_factor` 基准集权限已确认（15000 分） |
| 排后（第二波） | `hm_list` / `hm_detail`（游资名录）、板块体系 `ths_index` / `ths_member`（事件传导骨架） | `mining/sources/sentiment.py` 扩展 / `data/ths_index.py` | 先验证 top_list 情绪族有效再补游资名录；板块体系工程量大，中期做一套（ths） |
| B 档市场上下文 | `index_daily` / `opt_daily` / `cb_daily` / `shibor` 等宏观利率 | 不进个股因子池，进 `context/` 模块（regime/风格开关） | 消费层（strategies）暂不动 |
| LLM 增强层（形态③） | 语料类（新闻/公告/研报原文，积分门槛更高） | 数值提取器（读公告提取盈利指引）→ 与 `report_rc` 做差 | **§5.1 待确认**：语料接口积分门槛；预期差族（Phase 3）落地验证后再上 |
| 放弃/降级（不做因子） | `fina_audit`（审计意见）、`pledge`（质押）、`disclosure_date`（披露日程）、`stk_surv`（调研）、`ths_hot`/`dc_hot`（热榜） | 归 risk 层（ST/审计/质押为排除性风险信号，非排序 alpha）或直接放弃（弱信号/与情绪族冗余） | — |

**将来写新阶段计划的引用要点**：
- **样板** = 本计划 Task 1-7 的模式：`data/` 模块（fetch + parquet 缓存 + PIT 清洗/面板化，仿 `earnings.py`）→ `factors/mining/sources/` 因子族（注册进 `registry._register_defaults`，被 `list_factors(kind="single")` 动态发现）→ `mining/pipeline.py` 分层验证（复用 `compute_size_liquidity_layers` / `compute_ic_by_layer` / `run_mining_screen`）
- 分层验证基础设施（本计划 Task 1-3）落定后**直接复用**，后续阶段无需重做；每个新数据源的接口字段需按 tushare 官方文档核实（本计划已核实 `moneyflow` / `daily_basic` 两个，字段事实见 Global Constraints）
- 每个新阶段独立成计划（与"每计划自产可用可测软件"一致），每阶段验收标准同 Task 9（真实验证 + 如实记录 + 不擅自调参）

## File Structure

| 文件 | 责任 |
|------|------|
| `src/data/fetcher.py`（修改） | `fetch_fundamentals` 扩展 `circ_mv`/`turnover_rate` 两字段 |
| `src/factors/ops/layering.py`（新建） | `compute_size_liquidity_layers` 层标签纯函数（每日截面三分位） |
| `src/factors/ops/evaluation.py`（修改） | 追加 `compute_ic_by_layer` 分层 IC 原语 |
| `src/data/moneyflow.py`（新建） | `fetch_moneyflow_by_date` + `build_moneyflow_panel`（fetch + 清洗 + 缓存 + 面板化） |
| `src/factors/mining/__init__.py`（新建） | mining 包（空 init，namespace 约束下显式建包） |
| `src/factors/mining/sources/__init__.py`（新建） | sources 包 |
| `src/factors/mining/sources/moneyflow.py`（新建） | 资金流因子族 3 个因子（吃含 moneyflow 列的宽表） |
| `src/factors/registry.py`（修改） | `_register_defaults` 注册资金流因子（tags=["moneyflow","mining"]） |
| `src/factors/mining/pipeline.py`（新建） | `run_mining_screen` 评估编排（数据准备 + 分层验证 + 适用域判定） |
| `src/config/loader.py`（修改） | `FACTOR_CLEAN_DEFAULTS` 加 mining 段 + `load_factor_clean_config` 校验 |
| `configs/factor_clean.yaml`（修改） | 追加 mining 段 |
| `src/yq/factors.py`（修改） | 追加 `factor mining-screen` 命令 |
| `tests/data/test_moneyflow.py`（新建） | moneyflow 数据管线单测（mock tushare） |
| `tests/factors/test_layering.py`（新建） | 层标签原语单测 |
| `tests/factors/test_evaluation_layering.py`（新建） | `compute_ic_by_layer` 单测 |
| `tests/factors/test_moneyflow_factors.py`（新建） | 资金流因子族单测 |
| `tests/factors/test_mining_pipeline.py`（新建） | `run_mining_screen` 端到端测试 |
| `tests/cli/test_mining_cmd.py`（新建） | CLI 测试 |
| `docs/data-schemas.md` / `docs/project-plan.md` / `docs/history.md` / `docs/factors-clean.md`（修改） | 契约同步 |

---

### Task 1: `fetch_fundamentals` 扩展 circ_mv / turnover_rate

**Files:**
- Modify: `src/data/fetcher.py`（`fetch_fundamentals` 函数）
- Test: `tests/data/test_moneyflow.py` 中本 task 的 2 个测试（文件 Task 4 才建全，本 task 先建文件只放本 task 测试）

**Interfaces:**
- Consumes: 无（改造既有函数）
- Produces: `fetch_fundamentals(date, cache_dir=None) -> pd.DataFrame`——返回列扩展为 `code, pe, pb, total_mv, circ_mv, turnover_rate`（circ_mv 与 total_mv 同单位**亿元**、turnover_rate 原样 %）；Task 2 的 `compute_size_liquidity_layers` 消费

- [ ] **Step 1: Write the failing test**

```python
"""tests/data/test_moneyflow.py — moneyflow 数据管线 + fetch_fundamentals 扩展单测。"""
from __future__ import annotations

import pandas as pd
import pytest

from data.fetcher import fetch_fundamentals


# ---------------------------------------------------------------------------
# Task 1: fetch_fundamentals 扩展 circ_mv / turnover_rate
# ---------------------------------------------------------------------------


def test_fetch_fundamentals_includes_circ_mv_and_turnover(monkeypatch, tmp_path):
    """daily_basic 返回含 circ_mv/turnover_rate；circ_mv 转亿元、turnover 原样。"""
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600519.SH"],
            "trade_date": ["20250102", "20250102"],
            "pe": [5.0, 30.0],
            "pb": [0.8, 10.0],
            "total_mv": [20_000_000, 200_000_000],  # 万元 → 2000 / 20000 亿元
            "circ_mv": [15_000_000, 180_000_000],   # 万元 → 1500 / 18000 亿元
            "turnover_rate": [1.5, 0.3],
        }
    )
    calls = {}

    class FakeApi:
        def daily_basic(self, **kwargs):
            calls.update(kwargs)
            return raw

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "ts", type("TS", (), {"pro_api": lambda t: FakeApi()})())
    monkeypatch.setattr(fetcher_mod, "_PROXY_URL", "http://mock")

    df = fetch_fundamentals("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns) == ["code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"]
    assert df["circ_mv"].tolist() == [1500.0, 18000.0]  # 万元 → 亿元
    assert df["total_mv"].tolist() == [2000.0, 20000.0]  # 既有逻辑保持
    assert df["turnover_rate"].tolist() == [1.5, 0.3]  # 原样
    assert "circ_mv" in calls["fields"] and "turnover_rate" in calls["fields"]
    assert set(df["code"]) == {"000001", "600519"}


def test_fetch_fundamentals_cache_hit_skips_api(monkeypatch, tmp_path):
    """缓存命中时不再调用 API，且返回列完整（含新字段）。"""
    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    (tmp_path / "20250102.parquet").write_bytes(
        pd.DataFrame(
            {
                "code": ["000001"],
                "pe": [5.0],
                "pb": [0.8],
                "total_mv": [2000.0],
                "circ_mv": [1500.0],
                "turnover_rate": [1.5],
            }
        ).to_parquet()
    )
    called = []

    class FakeApi:
        def daily_basic(self, **kwargs):
            called.append(kwargs)
            return pd.DataFrame()

    import data.fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "ts", type("TS", (), {"pro_api": lambda t: FakeApi()})())

    df = fetch_fundamentals("2025-01-02", cache_dir=tmp_path)
    assert called == []  # 未调 API
    assert "circ_mv" in df.columns and "turnover_rate" in df.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_moneyflow.py -q`
Expected: FAIL（`AssertionError`：返回列缺 `circ_mv`/`turnover_rate`）

- [ ] **Step 3: Write minimal implementation**

修改 `src/data/fetcher.py` 的 `fetch_fundamentals`：

```python
    raw = api.daily_basic(
        trade_date=date_str,
        fields="ts_code,trade_date,pe,pb,total_mv,circ_mv,turnover_rate",
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"]
        )

    df = raw.rename(columns={"ts_code": "code"})
    df["code"] = df["code"].str.split(".").str[0]
    # total_mv / circ_mv 单位万元 → 亿元；turnover_rate 原样（%）
    df["total_mv"] = df["total_mv"] / 10_000
    df["circ_mv"] = df["circ_mv"] / 10_000

    cache_dir.mkdir(parents=True, exist_ok=True)
    df[["code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"]].to_parquet(
        cache_file, index=False
    )

    return df[["code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"]]
```

（同步把函数 docstring 的返回列说明更新为含新字段；空返回分支的列名列表也要改。）

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_moneyflow.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/fetcher.py tests/data/test_moneyflow.py
git commit -m "feat(data): fetch_fundamentals 扩展 circ_mv/turnover_rate（分层验证数据基础）"
```

---

### Task 2: `compute_size_liquidity_layers` 层标签原语

**Files:**
- Create: `src/factors/ops/layering.py`
- Test: `tests/factors/test_layering.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `fetch_fundamentals` 输出（date/code/circ_mv/turnover_rate 面板）
- Produces: `compute_size_liquidity_layers(basic_df, *, bins=3) -> pd.DataFrame`——与 `basic_df` 行对齐的 `(date, code, size_layer, liq_layer)`；size_layer ∈ {small, mid, large}、liq_layer ∈ {low, mid, high}（每维按当日截面三分位）；对应值 NaN 时该维层为 NaN；Task 6 的 `run_mining_screen` 消费

- [ ] **Step 1: Write the failing test**

```python
"""tests/factors/test_layering.py — 分层标签原语单测。"""
import numpy as np
import pandas as pd

from factors.ops.layering import compute_size_liquidity_layers


def _basic_df(n_days=3, n_stocks=6):
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            # circ_mv 递增（0..5），turnover 递减（5..0）→ 截面分位确定
            rows.append(
                {
                    "date": d,
                    "code": f"{600000 + i}",
                    "circ_mv": float(i * 100),
                    "turnover_rate": float((n_stocks - 1 - i) * 1.0),
                }
            )
    return pd.DataFrame(rows)


def test_layers_tercile_per_day():
    df = _basic_df(n_days=2, n_stocks=6)
    out = compute_size_liquidity_layers(df)
    assert list(out.columns) == ["date", "code", "size_layer", "liq_layer"]
    assert len(out) == len(df)
    # 每日截面：circ_mv 最小 1/3 → small；turnover 最大 1/3 → high
    day0 = out[out["date"] == out["date"].iloc[0]]
    assert set(day0.loc[day0["size_layer"] == "small", "code"]) == {"600000", "600001"}
    assert set(day0.loc[day0["size_layer"] == "large", "code"]) == {"600004", "600005"}
    assert set(day0.loc[day0["liq_layer"] == "high", "code"]) == {"600000", "600001"}
    assert set(day0.loc[day0["liq_layer"] == "low", "code"]) == {"600004", "600005"}


def test_layers_daily_cross_section_not_global():
    """分层按每日截面（不是全局分位）：日期间市值互换仍各自三分。"""
    dates = pd.bdate_range("2025-06-02", periods=2)
    rows = []
    for d, base in zip(dates, (0.0, 1000.0)):
        for i in range(6):
            rows.append({"date": d, "code": f"{600000 + i}", "circ_mv": base + i * 100.0, "turnover_rate": 1.0})
    df = pd.DataFrame(rows)
    out = compute_size_liquidity_layers(df)
    # 两天各自的 small 都是最小两只（600000/600001），不受整体水平影响
    for d in dates:
        day = out[out["date"] == d]
        assert set(day.loc[day["size_layer"] == "small", "code"]) == {"600000", "600001"}


def test_layers_nan_value_gives_nan_layer():
    df = _basic_df(n_days=1, n_stocks=6)
    df.loc[0, "circ_mv"] = np.nan
    df.loc[1, "turnover_rate"] = np.nan
    out = compute_size_liquidity_layers(df)
    assert pd.isna(out.loc[0, "size_layer"])
    assert pd.isna(out.loc[1, "liq_layer"])
    # 其他行不受影响
    assert out.loc[2, "size_layer"] == "small"


def test_layers_min_rows_falls_back_rank():
    """当日有效样本过少（< bins×2）时用 rank 分位降级，仍不报错。"""
    df = pd.DataFrame(
        {
            "date": ["2025-06-02"] * 4,
            "code": ["A", "B", "C", "D"],
            "circ_mv": [1.0, 2.0, 3.0, 4.0],
            "turnover_rate": [4.0, 3.0, 2.0, 1.0],
        }
    )
    out = compute_size_liquidity_layers(df)
    assert out["size_layer"].notna().all() and out["liq_layer"].notna().all()
    assert sorted(out["size_layer"].unique()) == ["large", "mid", "small"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_layering.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'factors.ops.layering'`）

- [ ] **Step 3: Write minimal implementation**

```python
"""factors/ops/layering.py — 分层标签纯函数（size × liquidity）。

每日截面三分位 → 每只股票当日的 size / liquidity 层标签。
分层是元数据（每股票每天一个标签），不是独立股票池。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_SIZE_LABELS = ["small", "mid", "large"]
_LIQ_LABELS = ["low", "mid", "high"]


def _tercile_labels(series: pd.Series, labels: list[str]) -> pd.Series:
    """单列每日截面三分位 → 层标签（对应值 NaN → NaN）。"""
    out = pd.Series(np.nan, index=series.index, dtype=object)
    valid = series.dropna()
    if len(valid) == 0:
        return out
    try:
        buckets = pd.qcut(valid, 3, labels=labels, duplicates="drop")
    except ValueError:
        # 有效样本过少/取值退化：用 rank 分位降级（1/3、2/3 断点）
        r = valid.rank(pct=True)
        buckets = pd.cut(
            r, [0.0, 1 / 3, 2 / 3, 1.0], labels=labels, include_lowest=True
        )
    out.loc[valid.index] = buckets
    return out


def compute_size_liquidity_layers(
    basic_df: pd.DataFrame,
    *,
    bins: int = 3,
) -> pd.DataFrame:
    """每日截面三分位 → size/liquidity 层标签。

    Parameters
    ----------
    basic_df : DataFrame
        含 ``date`` / ``code`` / ``circ_mv``（流通市值）/ ``turnover_rate``（换手率）。
    bins : int
        分位数桶数，默认 3（tercile）。仅支持 2/3。

    Returns
    -------
    DataFrame
        与 ``basic_df`` 行对齐，列：date, code, size_layer, liq_layer；
        size_layer ∈ {small, mid, large}、liq_layer ∈ {low, mid, high}；
        对应维度值为 NaN 时该维层为 NaN。
    """
    if bins not in (2, 3):
        raise ValueError(f"bins 仅支持 2/3，收到 {bins!r}")
    labels = _SIZE_LABELS[:bins] if bins == 3 else ["small", "large"]
    result = basic_df[["date", "code"]].copy()
    result["size_layer"] = _tercile_labels(basic_df["circ_mv"], labels)
    result["liq_layer"] = _tercile_labels(basic_df["turnover_rate"], _LIQ_LABELS[:bins] if bins == 3 else ["low", "high"])
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_layering.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/layering.py tests/factors/test_layering.py
git commit -m "feat(factors): 分层标签原语 compute_size_liquidity_layers（每日截面三分位）"
```

---

### Task 3: `compute_ic_by_layer` 分层 IC 原语

**Files:**
- Modify: `src/factors/ops/evaluation.py`
- Test: `tests/factors/test_evaluation_layering.py`（新建）

**Interfaces:**
- Consumes: `evaluation.py` 既有 `compute_ic` / `compute_ir`；Task 2 的层标签 DataFrame
- Produces: `compute_ic_by_layer(factor_df, factor_name, forward_return, layer_df, *, min_obs=5, min_days=10) -> pd.DataFrame`——index = `["all"] + [f"{s}-{l}" for s in size for l in liq]`（9 层），列 `mean_ic / t_stat / n_days`；层有效天数 < min_days 时 t_stat 为 NaN；Task 6 消费

- [ ] **Step 1: Write the failing test**

```python
"""tests/factors/test_evaluation_layering.py — compute_ic_by_layer 单测。"""
import numpy as np
import pandas as pd

from factors.ops.evaluation import compute_ic_by_layer


def _make_data(n_days=30, n_per_layer=8, seed=0):
    """每层股票因子值与 forward return 强相关（层内），构造可预期分层 IC。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows, fwd = [], []
    layers = ["small-low", "small-high", "mid-low", "mid-high", "large-low", "large-high"]
    for d in dates:
        for li, layer in enumerate(layers):
            s, l = layer.split("-")
            for k in range(n_per_layer):
                code = f"{600000 + li * 100 + k}"
                x = rng.normal(size=1)[0]
                y = x * 0.5 + rng.normal(scale=0.1)[0]  # 层内强相关
                rows.append({"date": d, "code": code, "f": x,
                             "size_layer": s, "liq_layer": l})
                fwd.append(y)
    factor_df = pd.DataFrame(rows)
    return factor_df[["date", "code", "f"]], pd.Series(fwd), factor_df[["date", "code", "size_layer", "liq_layer"]]


def test_ic_by_layer_structure_and_correlation():
    factor_df, fwd, layers = _make_data()
    out = compute_ic_by_layer(factor_df, "f", fwd, layers)
    assert list(out.index) == ["all"] + [
        f"{s}-{l}" for s in ("small", "mid", "large") for l in ("low", "mid", "high")
    ]
    for col in ("mean_ic", "t_stat", "n_days"):
        assert col in out.columns
    # 层内强正相关 → 每层 mean_ic > 0 且 t 显著
    assert (out["mean_ic"] > 0.2).all()
    assert (out["t_stat"] > 2).all()
    assert (out["n_days"] == 30).all()


def test_ic_by_layer_weak_layer_reported_not_dropped():
    """弱层如实报告（低 t），不静默剔除。"""
    factor_df, fwd, layers = _make_data(seed=1)
    # 把 small-low 层的因子值打乱 → 该层 IC 接近 0
    mask = (layers["size_layer"] == "small") & (layers["liq_layer"] == "low")
    rng = np.random.default_rng(99)
    factor_df.loc[mask, "f"] = rng.permutation(factor_df.loc[mask, "f"].to_numpy())
    out = compute_ic_by_layer(factor_df, "f", fwd, layers)
    assert abs(out.loc["small-low", "mean_ic"]) < 0.15  # 弱层低 IC 但仍在表里
    assert "small-low" in out.index


def test_ic_by_layer_short_history_nan_t():
    """层有效天数 < min_days → t_stat NaN（n_days 仍如实记录）。"""
    factor_df, fwd, layers = _make_data(n_days=5)
    out = compute_ic_by_layer(factor_df, "f", fwd, layers, min_days=10)
    assert (out["t_stat"].isna()).all()
    assert (out["n_days"] == 5).all()
    assert out["mean_ic"].notna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_evaluation_layering.py -q`
Expected: FAIL（`ImportError: cannot import name 'compute_ic_by_layer'`）

- [ ] **Step 3: Write minimal implementation**

追加到 `src/factors/ops/evaluation.py`（`compute_quantile_returns` 之前）：

```python
def compute_ic_by_layer(
    factor_df: pd.DataFrame,
    factor_name: str,
    forward_return: pd.Series,
    layer_df: pd.DataFrame,
    *,
    min_obs: int = 5,
    min_days: int = 10,
) -> pd.DataFrame:
    """全市场 + 按层分组的日频截面 IC 面板。

    Parameters
    ----------
    factor_df : DataFrame
        含 ``date`` / ``code`` / ``factor_name`` 列。
    forward_return : Series
        与 ``factor_df`` 行对齐的 forward return。
    layer_df : DataFrame
        含 ``date, code, size_layer, liq_layer``；按 ``(date, code)`` 与
        ``factor_df`` 对齐（行序无关）。
    min_obs : int
        单日单层截面有效样本下限（低于跳过当日）。
    min_days : int
        层有效天数下限；低于则 ``t_stat`` 为 NaN（n_days 仍记录）。

    Returns
    -------
    DataFrame
        index = ``["all"] + 9 层组合``（{size}-{liq}），列：
        mean_ic（IC 时序均值）、t_stat（mean/std×√n，std=0 → inf）、n_days。
    """
    merged = factor_df[["date", "code", factor_name]].copy()
    merged["__fwd__"] = forward_return.to_numpy(dtype=float)
    # 层标签按 (date, code) 对齐（行序无关，宽表与层表可能来自不同源）
    merged = merged.merge(
        layer_df[["date", "code", "size_layer", "liq_layer"]],
        on=["date", "code"],
        how="left",
    )

    def _stats(sub: pd.DataFrame) -> tuple[float, float, int]:
        ic = compute_ic(sub, factor_name, sub["__fwd__"], min_obs=min_obs)
        n = len(ic)
        if n == 0:
            return float("nan"), float("nan"), 0
        mean = float(ic.mean())
        t = float(compute_ir(ic) * np.sqrt(n))  # std=0 → inf（同 rolling_tstat 语义）
        return mean, t, n

    rows: dict[str, dict] = {}
    rows["all"] = dict(zip(("mean_ic", "t_stat", "n_days"), _stats(merged)))
    for size in ("small", "mid", "large"):
        for liq in ("low", "mid", "high"):
            sub = merged[
                (merged["size_layer"] == size) & (merged["liq_layer"] == liq)
            ]
            mean, t, n = _stats(sub)
            rows[f"{size}-{liq}"] = {"mean_ic": mean, "t_stat": t, "n_days": n}
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.loc[out["n_days"] < min_days, "t_stat"] = float("nan")
    return out[["mean_ic", "t_stat", "n_days"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_evaluation_layering.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/ops/evaluation.py tests/factors/test_evaluation_layering.py
git commit -m "feat(factors): compute_ic_by_layer 分层 IC 面板原语（全市场 + 9 层）"
```

---

### Task 4: moneyflow 数据管线

**Files:**
- Create: `src/data/moneyflow.py`
- Test: `tests/data/test_moneyflow.py`（追加本 task 3 个测试）

**Interfaces:**
- Consumes: tushare `moneyflow` 接口（字段已核实：`ts_code/trade_date/buy_sm_vol/buy_sm_amount/.../net_mf_vol/net_mf_amount`，金额万元）；`data/storage.py` 无依赖（直接 parquet 读写）
- Produces:
  - `fetch_moneyflow_by_date(date, cache_dir=None) -> pd.DataFrame`——单日全市场（date, code + 全部 moneyflow 字段，金额保持万元），缓存 `data/raw/moneyflow/{yyyymmdd}.parquet`
  - `build_moneyflow_panel(start, end, cache_dir=None, sleep_sec=0.3) -> pd.DataFrame`——批量拉取合并长表（按交易日历遍历，跳过缓存）；Task 5 因子输入与 Task 6 编排消费

- [ ] **Step 1: Write the failing test**

```python
# ---------------------------------------------------------------------------
# Task 4: moneyflow 数据管线
# ---------------------------------------------------------------------------


def test_fetch_moneyflow_by_date_shape_and_cache(monkeypatch, tmp_path):
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600519.SH"],
            "trade_date": ["20250102", "20250102"],
            "buy_sm_vol": [100, 200],
            "buy_sm_amount": [10.0, 20.0],
            "sell_sm_vol": [50, 60],
            "sell_sm_amount": [5.0, 6.0],
            "buy_md_vol": [30, 40],
            "buy_md_amount": [3.0, 4.0],
            "sell_md_vol": [10, 20],
            "sell_md_amount": [1.0, 2.0],
            "buy_lg_vol": [20, 30],
            "buy_lg_amount": [2.0, 3.0],
            "sell_lg_vol": [5, 10],
            "sell_lg_amount": [0.5, 1.0],
            "buy_elg_vol": [10, 5],
            "buy_elg_amount": [1.0, 0.5],
            "sell_elg_vol": [2, 3],
            "sell_elg_amount": [0.2, 0.3],
            "net_mf_vol": [90, 150],
            "net_mf_amount": [9.0, 15.0],
        }
    )
    calls = []

    class FakeApi:
        def moneyflow(self, **kwargs):
            calls.append(kwargs)
            return raw

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(mf_mod, "ts", type("TS", (), {"pro_api": lambda t: FakeApi()})())
    monkeypatch.setattr(mf_mod, "_PROXY_URL", "http://mock")

    df = mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns)[:3] == ["date", "code", "buy_sm_vol"]
    assert "net_mf_amount" in df.columns
    assert df["date"].iloc[0] == pd.Timestamp("2025-01-02")
    assert set(df["code"]) == {"000001", "600519"}
    assert df["net_mf_amount"].tolist() == [9.0, 15.0]  # 万元保持
    # 缓存命中不再调用
    df2 = mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert len(calls) == 1


def test_fetch_moneyflow_by_date_empty(monkeypatch, tmp_path):
    class FakeApi:
        def moneyflow(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(mf_mod, "ts", type("TS", (), {"pro_api": lambda t: FakeApi()})())
    df = mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns) == ["date", "code"]  # 空表仍保有基础列


def test_build_moneyflow_panel_merges_dates(monkeypatch, tmp_path):
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["20250102"],
            "buy_sm_vol": [100],
            "buy_sm_amount": [10.0],
            "sell_sm_vol": [50],
            "sell_sm_amount": [5.0],
            "buy_md_vol": [30],
            "buy_md_amount": [3.0],
            "sell_md_vol": [10],
            "sell_md_amount": [1.0],
            "buy_lg_vol": [20],
            "buy_lg_amount": [2.0],
            "sell_lg_vol": [5],
            "sell_lg_amount": [0.5],
            "buy_elg_vol": [10],
            "buy_elg_amount": [1.0],
            "sell_elg_vol": [2],
            "sell_elg_amount": [0.2],
            "net_mf_vol": [90],
            "net_mf_amount": [9.0],
        }
    )

    class FakeApi:
        def moneyflow(self, **kwargs):
            # 按 trade_date 参数返回对应日期数据
            td = kwargs.get("trade_date", "")
            return raw.assign(trade_date=td)

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(mf_mod, "ts", type("TS", (), {"pro_api": lambda t: FakeApi()})())
    monkeypatch.setattr(
        mf_mod,
        "fetch_trade_dates",
        lambda start, end: [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03")],
    )
    panel = mf_mod.build_moneyflow_panel(
        "2025-01-02", "2025-01-03", cache_dir=tmp_path, sleep_sec=0
    )
    assert len(panel) == 2
    assert sorted(panel["date"].unique()) == [
        pd.Timestamp("2025-01-02"),
        pd.Timestamp("2025-01-03"),
    ]
    assert "net_mf_amount" in panel.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/data/test_moneyflow.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'data.moneyflow'`）

- [ ] **Step 3: Write minimal implementation**

```python
"""data/moneyflow.py — 个股资金流数据管线（tushare moneyflow）。

仿 data/earnings.py：fetch（按交易日拉全市场，单次 ≤6000 行）+ 清洗
（ts_code 拆分、trade_date 转 date）+ parquet 缓存 + 面板化。
金额单位保持万元（与 daily_basic 的 circ_mv 万元同单位，可直接相除）。
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts
from dotenv import load_dotenv

from data.trade_calendar import fetch_trade_dates

load_dotenv()

#: moneyflow 接口金额/量字段（全部保留，因子层按需取列）
_MF_COLS = [
    "buy_sm_vol", "buy_sm_amount", "sell_sm_vol", "sell_sm_amount",
    "buy_md_vol", "buy_md_amount", "sell_md_vol", "sell_md_amount",
    "buy_lg_vol", "buy_lg_amount", "sell_lg_vol", "sell_lg_amount",
    "buy_elg_vol", "buy_elg_amount", "sell_elg_vol", "sell_elg_amount",
    "net_mf_vol", "net_mf_amount",
]

_PROXY_URL = "http://127.0.0.1:7890"


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "moneyflow"


def fetch_moneyflow_by_date(
    date: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """拉取单日全市场个股资金流（tushare moneyflow）。

    Parameters
    ----------
    date : str
        交易日期 "YYYY-MM-DD"。
    cache_dir : Path | None
        缓存目录；None 用 ``data/raw/moneyflow/``。

    Returns
    -------
    DataFrame
        列：date, code + ``_MF_COLS``（金额万元）。缓存命中直接读 parquet。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")
    cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
    date_str = date.replace("-", "")
    cache_file = cache_dir / f"{date_str}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL
    raw = api.moneyflow(trade_date=date_str)

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "code"])

    df = raw.rename(columns={"ts_code": "code", "trade_date": "date"})
    df["code"] = df["code"].str.split(".").str[0]
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = df[["date", "code"] + _MF_COLS]

    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache_file, index=False)
    return out


def build_moneyflow_panel(
    start: str,
    end: str,
    cache_dir: Path | str | None = None,
    sleep_sec: float = 0.3,
) -> pd.DataFrame:
    """批量拉取区间内每个交易日的资金流，合并为长表。

    Parameters
    ----------
    start / end : str
        日期范围 "YYYY-MM-DD"。
    cache_dir : Path | None
        缓存目录（透传 fetch_moneyflow_by_date）。
    sleep_sec : float
        未缓存调用之间的限频 sleep 秒数。

    Returns
    -------
    DataFrame
        date/code + ``_MF_COLS`` 长表（已按 date 升序排序）。
    """
    dates = fetch_trade_dates(start, end)
    frames = []
    for d in dates:
        frames.append(fetch_moneyflow_by_date(str(d.date()), cache_dir=cache_dir))
        if sleep_sec > 0:
            import time

            time.sleep(sleep_sec)
    if not frames:
        return pd.DataFrame(columns=["date", "code"] + _MF_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values("date").reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/data/test_moneyflow.py -q`
Expected: 5 passed（Task 1 的 2 个 + 本 task 3 个）

- [ ] **Step 5: Commit**

```bash
git add src/data/moneyflow.py tests/data/test_moneyflow.py
git commit -m "feat(data): moneyflow 资金流数据管线（fetch + 缓存 + 面板化）"
```

---

### Task 5: 资金流因子族 + 注册

**Files:**
- Create: `src/factors/mining/__init__.py`、`src/factors/mining/sources/__init__.py`、`src/factors/mining/sources/moneyflow.py`
- Modify: `src/factors/registry.py`（`_register_defaults` 追加注册）
- Test: `tests/factors/test_moneyflow_factors.py`（新建）

**Interfaces:**
- Consumes: Task 4 的 moneyflow 面板（date/code + `_MF_COLS`）+ daily_basic 的 `circ_mv`（宽表列）
- Produces: 3 个注册因子（`run_factor` 可调、`list_factors(kind="single")` 可见）：
  - `calc_moneyflow_net_ratio`：主力净流入强度 = `net_mf_amount / circ_mv`（万元相除，无量纲）
  - `calc_moneyflow_streak`：连续净流入天数（`net_mf_amount > 0` 连续计数，按 code 分组、日期升序）
  - `calc_moneyflow_big_net_ratio`：大单+特大单净额占比 = `(buy_lg_amount+buy_elg_amount-sell_lg_amount-sell_elg_amount) / (四档买+卖金额总和)`

- [ ] **Step 1: Write the failing test**

```python
"""tests/factors/test_moneyflow_factors.py — 资金流因子族单测。"""
import numpy as np
import pandas as pd

from factors.mining.sources.moneyflow import (
    calc_moneyflow_big_net_ratio,
    calc_moneyflow_net_ratio,
    calc_moneyflow_streak,
)
from factors.registry import list_factors, run_factor


def _mf_df(n_days=5, codes=("600000", "600001")):
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for c in codes:
            rows.append(
                {
                    "date": d, "code": c,
                    "buy_sm_amount": 100.0, "sell_sm_amount": 80.0,
                    "buy_md_amount": 50.0, "sell_md_amount": 40.0,
                    "buy_lg_amount": 20.0, "sell_lg_amount": 10.0,
                    "buy_elg_amount": 10.0, "sell_elg_amount": 5.0,
                    "net_mf_amount": 30.0, "circ_mv": 1000.0,
                }
            )
    # 600001 最后两天净流出 → streak 归零
    df = pd.DataFrame(rows)
    df.loc[(df["code"] == "600001") & (df["date"] >= dates[-2]), "net_mf_amount"] = -10.0
    return df


def test_moneyflow_net_ratio():
    df = _mf_df()
    s = calc_moneyflow_net_ratio(df)
    assert s.name == "moneyflow_net_ratio"
    assert abs(s.iloc[0] - 30.0 / 1000.0) < 1e-9  # 净流入/流通市值
    assert np.isnan(s.iloc[0]) is False


def test_moneyflow_net_ratio_missing_circ_mv_nan():
    df = _mf_df().drop(columns=["circ_mv"])
    s = calc_moneyflow_net_ratio(df)
    assert s.isna().all()  # 缺列 → 全 NaN（上游宽表准备层负责保证列存在）


def test_moneyflow_streak_counts_consecutive():
    df = _mf_df()
    s = calc_moneyflow_streak(df)
    # 600000 全期净流入 → 第 5 天 streak = 5；600001 第 3 天后转负 → 第 4 天归 0
    c0 = df["code"] == "600000"
    assert s[c0].iloc[-1] == 5
    c1 = df["code"] == "600001"
    assert s[c1].iloc[3] == 0
    assert s[c1].iloc[4] == 0  # 连续为负不计正 streak


def test_moneyflow_big_net_ratio():
    df = _mf_df()
    s = calc_moneyflow_big_net_ratio(df)
    # (20+10-10-5) / (100+80+50+40+20+10+10+5) = 15/315
    assert abs(s.iloc[0] - 15.0 / 315.0) < 1e-9


def test_moneyflow_factors_registered():
    names = list_factors(kind="single")
    assert "calc_moneyflow_net_ratio" in names
    assert "calc_moneyflow_streak" in names
    assert "calc_moneyflow_big_net_ratio" in names
    # run_factor 可调（缺列 → 全 NaN，不抛错）
    df = pd.DataFrame({"date": ["2025-06-02"], "code": ["600000"]})
    out = run_factor("calc_moneyflow_net_ratio", df)
    assert out.isna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_moneyflow_factors.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'factors.mining'`）

- [ ] **Step 3: Write minimal implementation**

`src/factors/mining/__init__.py` 与 `src/factors/mining/sources/__init__.py` 均为空文件（建包）。

`src/factors/mining/sources/moneyflow.py`：

```python
"""factors/mining/sources/moneyflow.py — 资金流因子族。

吃含 moneyflow 列与 circ_mv 的宽表（date/code 行对齐），输出截面因子值。
金额单位：net_mf_amount / circ_mv 均为万元（同单位相除，无量纲）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calc_moneyflow_net_ratio(df: pd.DataFrame) -> pd.Series:
    """主力净流入强度：net_mf_amount / circ_mv（万元相除）。"""
    if "circ_mv" not in df.columns:
        return pd.Series(np.nan, index=df.index, name="moneyflow_net_ratio")
    out = df["net_mf_amount"] / df["circ_mv"]
    return out.rename("moneyflow_net_ratio")


def calc_moneyflow_streak(df: pd.DataFrame) -> pd.Series:
    """连续净流入天数（net_mf_amount > 0 的连续计数，按 code 分组日期升序）。"""
    tmp = df[["date", "code", "net_mf_amount"]].copy()
    tmp["__pos__"] = (tmp["net_mf_amount"] > 0).astype(int)
    tmp["__grp__"] = (
        tmp.groupby("code")["__pos__"].transform(
            lambda x: (x != x.shift()).cumsum()
        )
    )
    streak = tmp.groupby(["code", "__grp__"])["__pos__"].cumsum()
    return pd.Series(streak.to_numpy(), index=df.index, name="moneyflow_streak")


def calc_moneyflow_big_net_ratio(df: pd.DataFrame) -> pd.Series:
    """大单+特大单净额占当日四档总金额比例。"""
    buy = df["buy_lg_amount"] + df["buy_elg_amount"]
    sell = df["sell_lg_amount"] + df["sell_elg_amount"]
    denom = (
        df["buy_sm_amount"] + df["sell_sm_amount"]
        + df["buy_md_amount"] + df["sell_md_amount"]
        + df["buy_lg_amount"] + df["sell_lg_amount"]
        + df["buy_elg_amount"] + df["sell_elg_amount"]
    )
    out = (buy - sell) / denom.replace(0, np.nan)
    return out.rename("moneyflow_big_net_ratio")
```

`src/factors/registry.py` 的 `_register_defaults()` 末尾追加：

```python
    from factors.mining.sources.moneyflow import (
        calc_moneyflow_big_net_ratio,
        calc_moneyflow_net_ratio,
        calc_moneyflow_streak,
    )

    register_factor(
        "calc_moneyflow_net_ratio", calc_moneyflow_net_ratio, tags=["moneyflow", "mining"]
    )
    register_factor(
        "calc_moneyflow_streak", calc_moneyflow_streak, tags=["moneyflow", "mining"]
    )
    register_factor(
        "calc_moneyflow_big_net_ratio",
        calc_moneyflow_big_net_ratio,
        tags=["moneyflow", "mining"],
    )
```

> 注：若 registry 已有 `_register_defaults` 之外的新因子注册入口（如装饰器），实现时保持一致机制；当前代码为手动注册。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_moneyflow_factors.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/mining/ src/factors/registry.py tests/factors/test_moneyflow_factors.py
git commit -m "feat(factors): 资金流因子族（净流入强度/连续天数/大单净占比）+ 注册"
```

---

### Task 6: `run_mining_screen` 评估编排

**Files:**
- Create: `src/factors/mining/pipeline.py`
- Test: `tests/factors/test_mining_pipeline.py`（新建）

**Interfaces:**
- Consumes: Task 1-5 全部产物（`fetch_fundamentals` 面板、`compute_size_liquidity_layers`、`compute_ic_by_layer`、moneyflow 面板、3 个资金流因子）；`factors/registry.run_factor`；`evaluation.compute_forward_returns`
- Produces: `run_mining_screen(*, ohlcv_path, basic_path, moneyflow_path, factors=None, fwd_window=5, min_obs=5, min_days=10, t_active=2.0, layer_t=2.81, output_dir=None) -> dict`——返回 `{screen: 评估表, layers: 层标签表, summary}`；`screen` 为 index=因子、列含 `mean_ic/t_stat/n_days + 9 层各列`；`summary` 含每因子 `domain`（"universal" / 显著层列表 / "none"）；output_dir 写 `screen.parquet` / `layers.parquet` / `summary.json`

- [ ] **Step 1: Write the failing test**

```python
"""tests/factors/test_mining_pipeline.py — run_mining_screen 端到端测试。"""
import json

import numpy as np
import pandas as pd

from factors.mining.pipeline import run_mining_screen


def _ohlcv(n_days=40, n_stocks=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "open": close - 0.05, "high": close + 0.1,
                    "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _basic(n_days=40, n_stocks=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "circ_mv": float(100 * (i + 1)),
                    "turnover_rate": float((n_stocks - i) * 0.5),
                }
            )
    return pd.DataFrame(rows)


def _moneyflow(n_days=40, n_stocks=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "buy_sm_amount": 100.0, "sell_sm_amount": 80.0,
                    "buy_md_amount": 50.0, "sell_md_amount": 40.0,
                    "buy_lg_amount": 20.0, "sell_lg_amount": 10.0,
                    "buy_elg_amount": 10.0, "sell_elg_amount": 5.0,
                    "net_mf_amount": float(rng.normal(30.0, 10.0)),
                }
            )
    return pd.DataFrame(rows)


def test_run_mining_screen_end_to_end(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv().to_parquet(ohlcv)
    _basic().to_parquet(basic)
    _moneyflow().to_parquet(mf)

    out = run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        factors=["calc_moneyflow_net_ratio"],
        fwd_window=5,
    )
    screen = out["screen"]
    assert "calc_moneyflow_net_ratio" in screen.index
    assert "all_mean_ic" in screen.columns
    assert "small-high_t_stat" in screen.columns
    assert "domain" in screen.columns
    assert out["summary"]["calc_moneyflow_net_ratio"]["domain"] in (
        "universal", "none",
    ) or isinstance(out["summary"]["calc_moneyflow_net_ratio"]["domain"], list)
    # 层标签表结构与因子宽表对齐
    assert list(out["layers"].columns) == ["date", "code", "size_layer", "liq_layer"]


def test_run_mining_screen_output_dir(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv(n_days=20, n_stocks=8).to_parquet(ohlcv)
    _basic(n_days=20, n_stocks=8).to_parquet(basic)
    _moneyflow(n_days=20, n_stocks=8).to_parquet(mf)
    out_dir = tmp_path / "out"

    run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        factors=["calc_moneyflow_net_ratio"],
        output_dir=out_dir,
    )
    assert (out_dir / "screen.parquet").exists()
    assert (out_dir / "layers.parquet").exists()
    summary = json.loads((out_dir / "summary.json").read_text())
    assert "calc_moneyflow_net_ratio" in summary


def test_run_mining_screen_all_three_factors(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    _basic(n_days=30, n_stocks=10).to_parquet(basic)
    _moneyflow(n_days=30, n_stocks=10).to_parquet(mf)

    out = run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        fwd_window=5,
    )  # factors=None → 默认资金流三因子
    assert list(out["screen"].index) == [
        "calc_moneyflow_net_ratio",
        "calc_moneyflow_streak",
        "calc_moneyflow_big_net_ratio",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/factors/test_mining_pipeline.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'factors.mining.pipeline'`）

- [ ] **Step 3: Write minimal implementation**

```python
"""factors/mining/pipeline.py — 因子挖掘评估编排（最小版）。

数据准备（ohlcv + daily_basic + moneyflow → 宽表）→ 因子值 →
全市场 + 分层 IC 验证 → 适用域判定。只读 parquet 产物，不 import data/ 与 analysis/。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from factors.mining.sources.moneyflow import (
    calc_moneyflow_big_net_ratio,
    calc_moneyflow_net_ratio,
    calc_moneyflow_streak,
)
from factors.ops.evaluation import compute_forward_returns, compute_ic_by_layer
from factors.ops.layering import compute_size_liquidity_layers
from factors.registry import run_factor

DEFAULT_MONEYFLOW_FACTORS = [
    "calc_moneyflow_net_ratio",
    "calc_moneyflow_streak",
    "calc_moneyflow_big_net_ratio",
]

_LAYER_COMBS = [
    f"{s}-{l}" for s in ("small", "mid", "large") for l in ("low", "mid", "high")
]


def _domain_for(row: pd.Series, t_active: float, layer_t: float) -> str | list[str]:
    """适用域判定：全市场 t ≥ t_active → universal；否则列出显著层（Bonferroni）。"""
    if row["all_t_stat"] >= t_active:
        return "universal"
    sig = [c.replace("_t_stat", "") for c in row.index
           if c.endswith("_t_stat") and c != "all_t_stat"
           and pd.notna(row[c]) and row[c] >= layer_t]
    return sig if sig else "none"


def run_mining_screen(
    *,
    ohlcv_path: Path,
    basic_path: Path,
    moneyflow_path: Path,
    factors: list[str] | None = None,
    fwd_window: int = 5,
    min_obs: int = 5,
    min_days: int = 10,
    t_active: float = 2.0,
    layer_t: float = 2.81,
    output_dir: Path | None = None,
) -> dict:
    """分层验证评估编排：因子 → 全市场 + 9 层 IC → 适用域标签。

    Parameters
    ----------
    ohlcv_path : Path
        行情 parquet（date/code/close + 状态列，forward return 与可交易性用）。
    basic_path : Path
        daily_basic parquet（date/code/circ_mv/turnover_rate，层标签用）。
    moneyflow_path : Path
        moneyflow 长表 parquet（date/code + 资金流列，因子输入）。
    factors : list[str] | None
        待评估因子名；None → 默认资金流三因子。
    fwd_window : int
        forward return 窗口（交易日）。
    min_obs / min_days : int
        透传 compute_ic_by_layer。
    t_active : float
        全市场显著阈值（与 monitor 一致，默认 2.0）。
    layer_t : float
        层显著阈值（Bonferroni 校正 n=10、α=0.05、双侧、大样本近似 z≈2.81）。
    output_dir : Path | None
        给定时写 screen.parquet / layers.parquet / summary.json。

    Returns
    -------
    dict
        键：screen（index=因子，列 = all_mean_ic/all_t_stat/all_n_days +
        9 层 × {mean_ic,t_stat,n_days} + domain）、layers（层标签表）、summary。
    """
    ohlcv = pd.read_parquet(ohlcv_path)
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    basic = pd.read_parquet(basic_path)
    basic["date"] = pd.to_datetime(basic["date"])
    mf = pd.read_parquet(moneyflow_path)
    mf["date"] = pd.to_datetime(mf["date"])

    # 宽表：ohlcv + daily_basic + moneyflow（按 date/code 对齐）
    wide = ohlcv.merge(basic[["date", "code", "circ_mv", "turnover_rate"]], on=["date", "code"], how="left")
    wide = wide.merge(mf, on=["date", "code"], how="left")

    layers = compute_size_liquidity_layers(basic)
    fwd = compute_forward_returns(ohlcv, [fwd_window])[fwd_window]

    factor_names = factors or DEFAULT_MONEYFLOW_FACTORS
    rows: dict[str, dict] = {}
    for f in factor_names:
        factor_series = run_factor(f, wide)
        ic_table = compute_ic_by_layer(
            wide, f, fwd, layers, min_obs=min_obs, min_days=min_days
        )
        flat: dict = {}
        for layer_name in ic_table.index:
            prefix = "all" if layer_name == "all" else layer_name
            flat[f"{prefix}_mean_ic"] = ic_table.loc[layer_name, "mean_ic"]
            flat[f"{prefix}_t_stat"] = ic_table.loc[layer_name, "t_stat"]
            flat[f"{prefix}_n_days"] = ic_table.loc[layer_name, "n_days"]
        rows[f] = flat
    screen = pd.DataFrame.from_dict(rows, orient="index")
    screen["domain"] = screen.apply(
        lambda r: _domain_for(r, t_active, layer_t), axis=1
    )

    summary = {f: {"domain": screen.loc[f, "domain"]} for f in factor_names}

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        screen.to_parquet(out / "screen.parquet")
        layers.to_parquet(out / "layers.parquet", index=False)
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    return {"screen": screen, "layers": layers, "summary": summary}
```

> 注：`compute_forward_returns` 返回 `{window: Series}` 且与传入 price_df 行对齐（`run_factor` 亦与 wide 行对齐）；`layer_df` 用 basic 原序与 `compute_ic_by_layer` 内部按 date/code merge 对齐，无需行序一致。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/factors/test_mining_pipeline.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/factors/mining/pipeline.py tests/factors/test_mining_pipeline.py
git commit -m "feat(factors): run_mining_screen 分层验证编排（全市场 + 9 层 IC + 适用域判定）"
```

---

### Task 7: CLI `yq factor mining-screen` + 配置

**Files:**
- Modify: `src/config/loader.py`、`configs/factor_clean.yaml`、`src/yq/factors.py`
- Test: `tests/cli/test_mining_cmd.py`（新建）、`tests/config/test_loader.py`（追加 1 个测试）

**Interfaces:**
- Consumes: Task 6 的 `run_mining_screen`；`FACTOR_CLEAN_DEFAULTS` / `load_factor_clean_config`（既有）
- Produces: `FACTOR_CLEAN_DEFAULTS` 新增 5 键（mining_t_active=2.0 / mining_layer_t=2.81 / mining_min_days=10 / mining_fwd_window=5 / mining_min_obs=5）+ `load_factor_clean_config` 校验（前 4 项正数）；CLI `yq factor mining-screen`

- [ ] **Step 1: Write the failing test（CLI）**

```python
"""tests/cli/test_mining_cmd.py — yq factor mining-screen CLI 测试。"""
import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from yq.cli import app

runner = CliRunner()


def _ohlcv(n_days=30, n_stocks=10, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "open": close - 0.05, "high": close + 0.1,
                    "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _basic(n_days=30, n_stocks=10, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "circ_mv": float(100 * (i + 1)),
                    "turnover_rate": float((n_stocks - i) * 0.5),
                }
            )
    return pd.DataFrame(rows)


def _moneyflow(n_days=30, n_stocks=10, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "buy_sm_amount": 100.0, "sell_sm_amount": 80.0,
                    "buy_md_amount": 50.0, "sell_md_amount": 40.0,
                    "buy_lg_amount": 20.0, "sell_lg_amount": 10.0,
                    "buy_elg_amount": 10.0, "sell_elg_amount": 5.0,
                    "net_mf_amount": float(rng.normal(30.0, 10.0)),
                }
            )
    return pd.DataFrame(rows)


def test_mining_screen_runs_and_json(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv().to_parquet(ohlcv)
    _basic().to_parquet(basic)
    _moneyflow().to_parquet(mf)
    result = runner.invoke(
        app, [
            "factor", "mining-screen",
            "--data", str(ohlcv), "--basic", str(basic),
            "--moneyflow", str(mf),
            "--fwd-window", "5",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "calc_moneyflow_net_ratio" in payload
    assert "domain" in payload["calc_moneyflow_net_ratio"]


def test_mining_screen_missing_input_exits_1(tmp_path):
    result = runner.invoke(
        app, [
            "factor", "mining-screen",
            "--data", str(tmp_path / "nope.parquet"),
            "--basic", str(tmp_path / "nope.parquet"),
            "--moneyflow", str(tmp_path / "nope.parquet"),
        ]
    )
    assert result.exit_code != 0
    assert "错误" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_mining_cmd.py -q`
Expected: FAIL（`No such command: 'mining-screen'`）

- [ ] **Step 3: Write minimal implementation**

`src/config/loader.py` 的 `FACTOR_CLEAN_DEFAULTS` 末尾追加：

```python
    # Phase 挖掘（因子挖掘分层验证）
    "mining_t_active": 2.0,
    "mining_layer_t": 2.81,
    "mining_min_days": 10,
    "mining_fwd_window": 5,
    "mining_min_obs": 5,
```

`load_factor_clean_config` 校验块末尾追加：

```python
    for key in ("mining_layer_t", "mining_t_active"):
        if not isinstance(cfg[key], (int, float)) or cfg[key] <= 0:
            raise ValueError(f"{key} 必须为正数，收到 {cfg[key]!r}")
    for key in ("mining_min_days", "mining_fwd_window", "mining_min_obs"):
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(f"{key} 必须为正整数，收到 {cfg[key]!r}")
```

`configs/factor_clean.yaml` 末尾追加：

```yaml
# Phase 挖掘（分层验证）
mining_t_active: 2.0     # 全市场显著阈值（与 monitor 一致）
mining_layer_t: 2.81     # 层显著阈值（Bonferroni 校正 n=10, α=0.05, 双侧）
mining_min_days: 10      # 层有效天数下限
mining_fwd_window: 5     # forward return 窗口（交易日）
mining_min_obs: 5        # 单日单层截面样本下限
```

`src/yq/factors.py` 追加（import 行加 `from factors.mining.pipeline import run_mining_screen`；`factor_clean_c` 之后）：

```python
@factor_app.command("mining-screen")
def factor_mining_screen(
    data: Path = typer.Option(..., "--data", help="全市场行情 parquet"),
    basic: Path = typer.Option(..., "--basic", help="daily_basic parquet（circ_mv/turnover_rate）"),
    moneyflow: Path = typer.Option(..., "--moneyflow", help="moneyflow 长表 parquet"),
    factors: str | None = typer.Option(None, "--factors", help="待评估因子（逗号分隔），缺省资金流三因子"),
    config: Path | None = typer.Option(None, "--config", help="factor_clean.yaml"),
    fwd_window: int | None = typer.Option(None, "--fwd-window", help="forward return 窗口"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="输出目录"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出 summary"),
):
    """因子挖掘分层验证：全市场 + 9 层 IC + 适用域判定。"""
    try:
        cfg = load_factor_clean_config(config) if config is not None else {}
        fwd_window = fwd_window if fwd_window is not None else int(
            cfg.get("mining_fwd_window", 5)
        )
        factor_list: list[str] | None = (
            [s.strip() for s in factors.split(",") if s.strip()]
            if factors is not None else None
        )
        out = run_mining_screen(
            ohlcv_path=data,
            basic_path=basic,
            moneyflow_path=moneyflow,
            factors=factor_list,
            fwd_window=fwd_window,
            min_obs=int(cfg.get("mining_min_obs", 5)),
            min_days=int(cfg.get("mining_min_days", 10)),
            t_active=float(cfg.get("mining_t_active", 2.0)),
            layer_t=float(cfg.get("mining_layer_t", 2.81)),
            output_dir=output_dir,
        )
        summary = out["summary"]
        if json_out:
            typer.echo(
                json.dumps(summary, ensure_ascii=False, indent=2, default=str)
            )
            return
        for fname, meta in summary.items():
            dom = meta["domain"]
            dom_str = dom if isinstance(dom, str) else ",".join(dom)
            typer.echo(f"{fname}: domain={dom_str}")
        if output_dir is not None:
            typer.echo(f"输出: {output_dir}")
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_mining_cmd.py -q`
Expected: 2 passed

- [ ] **Step 5: 配置校验测试补绿**

在 `tests/config/test_loader.py` 追加：

```python
def test_load_factor_clean_config_mining_defaults_and_validation(tmp_path):
    p = tmp_path / "factor_clean.yaml"
    p.write_text("mining_layer_t: 3.0\nmining_min_days: 20\n", encoding="utf-8")
    cfg = load_factor_clean_config(p)
    assert cfg["mining_layer_t"] == 3.0
    assert cfg["mining_min_days"] == 20
    assert cfg["mining_t_active"] == 2.0  # 缺省合并
    p.write_text("mining_min_days: 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_factor_clean_config(p)
```

Run: `.venv/bin/python -m pytest tests/config/ -q`
Expected: PASS（既有 + 新增全绿；若 `load_factor_clean_config` 测试文件路径不同，按实际追加）

- [ ] **Step 6: Commit**

```bash
git add src/config/loader.py configs/factor_clean.yaml src/yq/factors.py \
        tests/cli/test_mining_cmd.py tests/config/test_loader.py
git commit -m "feat(yq): factor mining-screen CLI + 挖掘分层验证配置"
```

---

### Task 8: 契约文档同步 + 全量回归

**Files:**
- Modify: `docs/data-schemas.md`、`docs/project-plan.md`、`docs/history.md`、`docs/factors-clean.md`

- [ ] **Step 1: data-schemas.md**

在因子清洗相关 schema 段追加：

```markdown
### Phase 挖掘 M1：分层验证 + moneyflow（factors/ops/layering.py + evaluation.py + data/moneyflow.py + factors/mining/）

- `fetch_fundamentals(date, cache_dir=None) -> DataFrame`：daily_basic，列 `code, pe, pb, total_mv, circ_mv, turnover_rate`（total_mv/circ_mv 亿元、turnover_rate %）
- `compute_size_liquidity_layers(basic_df, *, bins=3) -> DataFrame`：每日截面三分位 → `(date, code, size_layer, liq_layer)`；size ∈ {small,mid,large}、liq ∈ {low,mid,high}；对应值为 NaN → 该维 NaN
- `compute_ic_by_layer(factor_df, factor_name, forward_return, layer_df, *, min_obs=5, min_days=10) -> DataFrame`：index = `["all"] + 9 层组合`，列 `mean_ic / t_stat / n_days`；有效天数 < min_days → t_stat NaN
- `fetch_moneyflow_by_date(date, cache_dir=None) -> DataFrame` / `build_moneyflow_panel(start, end, ...)`：moneyflow 长表（date/code + 18 个资金流字段，金额万元）
- 因子（注册 `factors/registry`，tags=["moneyflow","mining"]）：`calc_moneyflow_net_ratio`（net_mf/circ_mv）、`calc_moneyflow_streak`（连续净流入天数）、`calc_moneyflow_big_net_ratio`（大单+特大单净额占比）
- `run_mining_screen(*, ohlcv_path, basic_path, moneyflow_path, factors=None, fwd_window=5, min_obs=5, min_days=10, t_active=2.0, layer_t=2.81, output_dir=None) -> dict`：键 `screen`（index=因子，all + 9 层 × {mean_ic,t_stat,n_days} + domain）、`layers`、`summary`；output_dir 写 screen.parquet / layers.parquet / summary.json
- 适用域判定：全市场 t ≥ t_active → "universal"；否则 Bonferroni 校正（layer_t=2.81）下显著层列表；无 → "none"
```

- [ ] **Step 2: project-plan.md**

把 `| context (因子选择) | 🔲 路线图 |` 行更新为：

```markdown
| context (因子选择) | 🔲 路线图 | Phase 挖掘 M1: factors/ops/layering.py + compute_ic_by_layer + data/moneyflow.py + factors/mining/（分层验证 + moneyflow 资金流族，见 factor-mining-phase1-plan.md） |
```

- [ ] **Step 3: history.md**

新增 Phase 30 段（仿 Phase 29 格式，写在文件末尾）：动机（量价同质化 → 另类数据源；分层验证防条件因子误杀）、分层口径（size×liquidity 两维 9 层、tercile、Bonferroni）、接口事实（moneyflow/daily_basic 字段与门槛）、Task 1-7 commit 摘要、全量回归数字。结果段（真实验证）留待 Task 9 补记。

- [ ] **Step 4: factors-clean.md**

§6 之后追加"## 7. 因子挖掘（分层验证 + 另类数据源）"小节，写设计说明（分层验证动机/口径、moneyflow 族、后续因子族路线），并标注实现状态。

- [ ] **Step 5: 全量回归 + ruff**

Run: `.venv/bin/python -m pytest -q`
Expected: **1142 + 新增（2 + 4 + 3 + 3 + 5 + 3 + 3 ≈ 23）≈ 1165 passed, 0 failed**（以实测为准）

Run: `.venv/bin/python -m ruff check src/data/fetcher.py src/data/moneyflow.py src/factors/ops/layering.py src/factors/ops/evaluation.py src/factors/mining/ src/factors/registry.py src/config/loader.py src/yq/factors.py tests/data/test_moneyflow.py tests/factors/test_layering.py tests/factors/test_evaluation_layering.py tests/factors/test_moneyflow_factors.py tests/factors/test_mining_pipeline.py tests/cli/test_mining_cmd.py && .venv/bin/python -m ruff format src/data/moneyflow.py src/factors/ops/layering.py src/factors/mining/pipeline.py src/factors/mining/sources/moneyflow.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add docs/data-schemas.md docs/project-plan.md docs/history.md docs/factors-clean.md
git commit -m "docs: 因子挖掘 M1 契约同步（分层验证 + moneyflow）"
```

---

### Task 9: 全市场真实验证

**Files:**
- Modify: `docs/history.md`

**输入：**
- ohlcv：`data/clean/full_market_ohlcv.parquet`
- daily_basic：本计划 Task 1 扩展后拉取（`data/raw/fundamentals/` 既有缓存仅 pe/pb/total_mv，需重拉含 circ_mv/turnover_rate 的版本）
- moneyflow：`data/raw/moneyflow/`（近 2 年，与 ohlcv 同窗口）

- [ ] **Step 1: 真实拉取**

Run（nohup 后台，预计 10-30 分钟，受限频影响；分两步）：
```bash
cd /Users/erwei/.hermes/project/yoyo-quant && mkdir -p data/audit/factor_mining_m1 data/raw/fundamentals data/raw/moneyflow
# 1) daily_basic 全窗口重拉（扩展后字段）
.venv/bin/python -c "
from data.fetcher import fetch_fundamentals
from data.trade_calendar import fetch_trade_dates
import time
dates = fetch_trade_dates('2023-08-07', '2026-07-31')  # 与 ohlcv 同窗口（按实际日历核对）
for i, d in enumerate(dates):
    fetch_fundamentals(str(d.date()))
    if i % 50 == 0: print('basic', i, d.date())
    time.sleep(0.3)
"
# 2) moneyflow 全窗口拉取
.venv/bin/python -c "
from data.moneyflow import build_moneyflow_panel
build_moneyflow_panel('2023-08-07', '2026-07-31')
"
```
Expected: 无异常；`data/raw/fundamentals/` 与 `data/raw/moneyflow/` 缓存目录文件数与交易日数一致

- [ ] **Step 2: 组装面板 + 跑 mining-screen**

Run:
```bash
cd /Users/erwei/.hermes/project/yoyo-quant && .venv/bin/python -c "
import pandas as pd
from data.trade_calendar import fetch_trade_dates
import glob, os
# 合并 daily_basic 缓存 → basic.parquet（含 circ_mv/turnover_rate）
frames = [pd.read_parquet(p) for p in sorted(glob.glob('data/raw/fundamentals/*.parquet'))]
basic = pd.concat(frames, ignore_index=True)
basic['date'] = pd.to_datetime(basic['date']) if 'date' in basic.columns else pd.to_datetime(basic['trade_date'], format='%Y%m%d')
basic.to_parquet('data/audit/factor_mining_m1/basic.parquet', index=False)
# 合并 moneyflow 缓存 → moneyflow.parquet
frames = [pd.read_parquet(p) for p in sorted(glob.glob('data/raw/moneyflow/*.parquet'))]
mf = pd.concat(frames, ignore_index=True)
mf.to_parquet('data/audit/factor_mining_m1/moneyflow.parquet', index=False)
print('basic rows:', len(basic), 'moneyflow rows:', len(mf))
"
.venv/bin/yq factor mining-screen \
  --data data/clean/full_market_ohlcv.parquet \
  --basic data/audit/factor_mining_m1/basic.parquet \
  --moneyflow data/audit/factor_mining_m1/moneyflow.parquet \
  --output-dir data/audit/factor_mining_m1 --json
```
Expected: exit 0；JSON 输出三因子 domain；`screen.parquet` / `layers.parquet` / `summary.json` 落盘

- [ ] **Step 3: 核对 + 记录 + 验收**

Run: `.venv/bin/python -c "
import json, pandas as pd
s = json.load(open('data/audit/factor_mining_m1/summary.json'))
print(s)
sc = pd.read_parquet('data/audit/factor_mining_m1/screen.parquet')
print(sc[['all_mean_ic','all_t_stat','domain']].to_string())
lay = pd.read_parquet('data/audit/factor_mining_m1/layers.parquet')
print('layers:', lay['size_layer'].value_counts().to_dict(), lay['liq_layer'].value_counts().to_dict())
"`

在 `docs/history.md` Phase 30 段补结果小节（命令、窗口、三因子 all/层 IC 摘要、domain 判定、结论）。**验收标准**：如实记录——资金流因子在全市场与各层的显著性分布；若某因子 domain 为显著层列表（如小盘层），正是分层验证价值的直接证据；若全部 none，如实记录（可能样本期/口径问题），按计划约定不擅自调参，记录后问用户。

Run: `.venv/bin/python -m pytest -q`
Expected: 全量回归仍绿

- [ ] **Step 4: Commit**

```bash
git add docs/history.md
git commit -m "docs: 因子挖掘 M1 全市场真实验证结果"
```

---

## Self-Review

**1. Spec coverage（design doc §3.4 + §2.6 + §4 + §6）：**
- §3.4 分层验证体系（size×liquidity 两维 9 层、tercile、Bonferroni、全层报告、适用域标签）→ Task 2（层标签）+ Task 3（分层 IC）+ Task 6（适用域判定）✅
- §2.6 moneyflow 第一优先接入 → Task 4（数据管线）+ Task 5（因子族）✅
- §4 数据层"每数据域一模块"（moneyflow.py 仿 earnings.py）→ Task 4 ✅；因子层注册进 registry 被 list_factors 发现 → Task 5 ✅；筛选流水线关卡 2（含分层验证）→ Task 3/6 ✅
- §6 factors/mining/ 结构 → Task 5（sources/moneyflow.py）+ Task 6（pipeline.py）✅（layering.py 为 §6 结构树的细化补充，属 ops/ 既有职责"对因子的操作"）
- 存量链路接管（clean-a/b/c）不属本计划（第一阶段只产出适用域标签评估表，monitor 接入标注为后续）✅ 范围声明
- §5 待确认 5（分层边界落地校准）→ Task 9 真实验证记录校准 ✅

**2. Placeholder scan：** 无 TBD/"类似 Task N"/"实现细节省略"。唯一实现时需核实点已显式标注：Task 5 注册机制（注明当前为手动注册，与既有 `_register_defaults` 一致）。`report_rc` 等未接入数据源不在本计划范围（Phase 1 只做 moneyflow）。

**3. Type consistency：**
- `compute_size_liquidity_layers(basic_df, *, bins=3) -> (date, code, size_layer, liq_layer)`：Task 2 定义，Task 6 消费（`layers = compute_size_liquidity_layers(basic)`）✅
- `compute_ic_by_layer(factor_df, factor_name, forward_return, layer_df, *, min_obs, min_days) -> DataFrame`：Task 3 定义，Task 6 消费（`compute_ic_by_layer(wide, f, fwd, layers, ...)`）✅
- `run_mining_screen(*, ohlcv_path, basic_path, moneyflow_path, factors, fwd_window, min_obs, min_days, t_active, layer_t, output_dir)`：Task 6 定义，Task 7 CLI 调用（参数名一一对应）✅
- 因子名 `calc_moneyflow_net_ratio / calc_moneyflow_streak / calc_moneyflow_big_net_ratio`：Task 5 注册，Task 6 默认列表 + Task 7 测试断言一致 ✅
- CLI 参数名 ↔ run_mining_screen：--fwd-window→fwd_window、--factors→factors、--output-dir→output_dir ✅
- `fetch_fundamentals` 列扩展 `circ_mv/turnover_rate`：Task 1 定义，Task 2 消费（circ_mv/turnover_rate 列）✅

**4. 已知偏差（计划内声明，非缺陷）：**
- 第一阶段不做 monitor 接入与 clean-a/b/c 存量链路（范围声明）；真实验证窗口取与 ohlcv 一致（2023-08-07 起）
- `_domain_for` 的层 t 阈值 2.81 为 Bonferroni 校正 n=10、α=0.05、双侧的大样本近似 z；自由度相关精确临界值可在 Task 9 校准（§5 待确认 5）
- compute_ic_by_layer 的 `compute_ic` 复用要求 sub 含 factor_name 列与 __fwd__ 列——实现按列名契约对齐，测试覆盖
