# 因子生命周期监控实现计划

> **For Hermes:** 按 task 逐个实现；每 task 走完整 TDD 循环（写失败测试 → 跑失败 → 最小实现 → 跑通过 → commit），实现前 invoke `karpathy-guidelines` skill。

**Goal:** 为日频交易者提供全市场量价因子的持续监控（active/decaying/dead 状态机 + 滚动 IC/IR/t 统计 + 图），支撑"因子失效就换"的决策。

**Architecture:** 纯计算下沉 `factors/evaluation.py`（滚动统计三函数）；状态机/持久化/编排在 `analysis/factor_monitor.py`（只依赖 factors.registry + factors.evaluation）；CLI 走 `yq factor monitor`；绘图在 `analysis/plot.py`。数据为 `data/clean/full_market_ohlcv.parquet`（已生成，含市场状态列）。

**Tech Stack:** Python 3.11+ / pandas / numpy / matplotlib / typer（yq CLI）/ pytest。

**前置状态：**
- 设计文档 `docs/factor-lifecycle-monitor-design.md`（f813d16）
- 全市场数据已就绪：`data/clean/full_market_ohlcv.parquet`（4999 股、2023-08-07 → 2026-08-05、354 万行、含 limit_up/limit_down/is_suspended）
- **数据代码 review 发现 5 个待修复问题（1 blocking + 4 high）→ Task 0 必须先做**

---

## Task 0：修复全市场数据质量（blocking + high，review 结论）

> 依据：`review` 完整报告（sa_20260805_134752）。数据标注错误会直接污染 IC 评估，必须先行修复并重新清洗。

### Task 0.1：修复北交所过滤回归（Blocking）

**Objective:** 43 开头北交所股票不再漏入股票池。

**Files:**
- Modify: `src/data/fetcher.py`（`fetch_all_stocks` 过滤处，约 :368）
- Test: `tests/data/test_fetcher.py`

**Step 1: 写失败测试**
```python
def test_fetch_all_stocks_excludes_bse_43x(monkeypatch):
    # stock_basic 返回含 430047（北交所 43x）的列表时，结果须排除
    ...
    codes = fetch_all_stocks(date="2026-08-05")["code"]
    assert not any(c.startswith(("4", "8", "920")) for c in codes)
```

**Step 2: 跑测试验证失败** → `pytest tests/data/test_fetcher.py -v`，预期 FAIL。

**Step 3: 修复**：优先用 `stock_basic` 的 `market` 字段过滤（`df["market"] == "北交所"` 剔除），最稳；若该字段不可用，前缀恢复为 `("4", "8", "920")`。

**Step 4: 跑测试验证通过** → 预期 PASS（含既有 830001/920000 用例）。

**Step 5: Commit**：`fix(data): 北交所过滤回归，剔除 43 开头股票`

### Task 0.2：修复涨跌停判定精度（High）

**Objective:** 涨停价四舍五入到分（`round(pre_close*(1+pct), 2)`），`eps=1e-8` 容不下，pre_close 含奇数分时漏判（如 10.03 → 涨停 11.03，涨幅仅 9.97%）。

**Files:**
- Modify: `src/data/filters.py` `detect_limit_price`（:60-62）
- Test: `tests/data/test_filters.py`

**Step 1: 写失败测试**
```python
def test_limit_up_rounding_to_fen():
    df = pd.DataFrame({
        "date": ["2026-01-02", "2026-01-05"],
        "code": ["000001"] * 2,
        "close": [10.03, 11.03],   # 11.03 == round(10.03*1.10, 2) 涨停
        "pre_close": [10.00, 10.03],
    })
    out = detect_limit_price(df)
    assert out["limit_up"].tolist() == [False, True]  # 现状为 False → 漏判
```

**Step 2: 跑测试验证失败** → 预期 FAIL。

**Step 3: 修复**：改价格比较——`limit_price = np.where(20%板, round(pre_close*1.20, 2), round(pre_close*(1+limit_pct), 2))`；`limit_up = close >= limit_price - 0.001`；`limit_down = close <= round(pre_close*(1-limit_pct), 2) + 0.001`（20% 板同理）。

**Step 4: 跑测试验证通过** → 预期 PASS。

**Step 5: Commit**：`fix(data): 涨跌停判定改为价格比较（四舍五入到分 + 0.001 容差）`

### Task 0.3：修复停牌补齐上界（High）

**Objective:** `fetch_full_market.py` 的 `END = date.today()`（自然日）使网格上界可能 > 行情实际最大日期 → 全市场最后 1-2 个交易日被误标 `is_suspended=True`。

**Files:**
- Modify: `src/data/filters.py` `detect_suspension`（网格上界）或 `notebooks/fetch_full_market.py`
- Test: `tests/data/test_filters.py`

**Step 1: 写失败测试**：构造 `trade_dates` 上界晚于行情最大日期的用例，断言补齐行不越过 `raw["date"].max()`。

**Step 2: 跑测试验证失败** → FAIL。

**Step 3: 修复**：上界取 `min(日历网格上界, df["date"].max())`。

**Step 4: 跑测试验证通过** → PASS。

**Step 5: Commit**：`fix(data): 停牌补齐上界裁剪到行情实际最大日期`

### Task 0.4：修复限频重试关键词（High）

**Objective:** tushare 限频错误文本「抱歉，您每分钟最多访问该接口X次」不含现有 `retryable` 关键词（过快/频率/unavailable/timeout），重试形同虚设。

**Files:**
- Modify: `src/data/fetcher.py`（:53 retryable 元组）
- Test: `tests/data/test_fetcher.py`

**Step 1: 写失败测试**：模拟 tushare 限频错误文本，断言走重试路径。

**Step 2: 跑测试验证失败** → FAIL。

**Step 3: 修复**：`retryable` 加入「每分钟」「最多访问」「访问次数」；`fetch_daily_batch` 的 sleep 支持按限频反馈自适应（可先固定 `sleep_sec` 可配置）。

**Step 4: 跑测试验证通过** → PASS。

**Step 5: Commit**：`fix(data): 限频重试匹配 tushare 官方错误文本`

### Task 0.5：移除硬编码 API 密钥（High）

**Files:**
- Delete or Modify: `notebooks/test_tushare.py`（:3 明文 `X-API-Key` + 明文代理 URL）

**Step 1:** 删除该文件，或改为从环境变量读取密钥。

**Step 2: Commit**：`fix(notebooks): 移除硬编码 API 密钥，改为环境变量注入`

### Task 0.6：停牌补齐幂等与性能（Medium，顺手修）

**Files:**
- Modify: `src/data/filters.py` `detect_suspension`
- Test: `tests/data/test_filters.py`

**Step 1: 写失败测试**：对已清洗输出再次运行 `detect_suspension`，断言补齐行仍为 `is_suspended=True`（现状 volume=NaN → `volume==0` 为 False → 被重标为未停牌）。

**Step 2: 跑测试验证失败** → FAIL。

**Step 3: 修复**：补齐行 `volume` 填 0（保持 `volume==0` 规则自洽）；顺手把逐股循环补行改为 `MultiIndex.from_product` 一次性 `reindex`（5000 股 × 730 日性能）。

**Step 4: 跑测试验证通过** → PASS。

**Step 5: Commit**：`fix(data): 停牌补齐 volume 填 0（幂等）+ MultiIndex 网格化`

### Task 0.7：重新清洗并验证全市场数据

**Step 1:** 重新运行 `notebooks/fetch_full_market.py`（raw 已缓存，主要开销在清洗）。

**Step 2: 验证**
```bash
.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/clean/full_market_ohlcv.parquet')
print(df['code'].nunique(), df['date'].min(), df['date'].max())
print('limit_up', int(df['limit_up'].sum()), 'limit_down', int(df['limit_down'].sum()), 'susp', int(df['is_suspended'].sum()))
# 抽查：无 4/8 开头代码；最后 3 个交易日不全为 is_suspended
assert not df['code'].astype(str).str.startswith(('4','8','920')).any()
tail = df[df['date'] >= df['date'].max() - pd.Timedelta(days=5)]
assert not tail['is_suspended'].all()
"
```
预期：无 4/8/920 代码；最后几交易日非全停牌。

**Step 3: Commit**：`data: 重新清洗全市场（修复后）`（或仅记录于 history.md，数据文件不入 git——按项目惯例 data/ 忽略情况处理）

---

## Task 1：evaluation.py 滚动原语（TDD）

### Task 1.1：compute_rolling_ic

**Objective:** 对日频 IC 时序做滚动窗口均值。

**Files:**
- Create: `tests/test_evaluation_rolling.py`
- Modify: `src/factors/evaluation.py`

**Step 1: 写失败测试**
```python
import numpy as np, pandas as pd
from factors.evaluation import compute_rolling_ic

def test_rolling_ic_basic():
    ic = pd.Series([1.0, 2.0, 3.0, 4.0], index=pd.date_range("2026-01-01", periods=4))
    out = compute_rolling_ic(ic, window=2)
    assert out.iloc[1] == 1.5 and out.iloc[2] == 2.5 and np.isnan(out.iloc[0])

def test_rolling_ic_min_periods():
    ic = pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2))
    out = compute_rolling_ic(ic, window=5, min_periods=2)
    assert out.iloc[-1] == 1.5  # 窗口不足但 min_periods 满足
```

**Step 2: 跑测试** → `pytest tests/test_evaluation_rolling.py -v`，预期 FAIL（函数不存在）。

**Step 3: 实现**
```python
def compute_rolling_ic(ic_series, window, min_periods=None):
    """滚动窗口 IC 均值。window >= 1；min_periods 缺省 = window。"""
    if window < 1:
        raise ValueError("window 必须 >= 1")
    min_periods = window if min_periods is None else min_periods
    return ic_series.rolling(window=window, min_periods=min_periods).mean()
```

**Step 4: 跑测试** → 预期 PASS。

**Step 5: Commit**：`feat(factors): compute_rolling_ic`

### Task 1.2：compute_rolling_ir

**Step 1: 写失败测试**：`compute_rolling_ir` 窗口内 mean/std(ddof=1)；std=0 → inf；单点窗口 → NaN；空序列 → 空。
```python
def test_rolling_ir_basic():
    ic = pd.Series([1.0, 2.0, 3.0, 4.0], index=pd.date_range("2026-01-01", periods=4))
    out = compute_rolling_ir(ic, window=2)
    assert abs(out.iloc[1] - (1.5 / np.std([1.0, 2.0], ddof=1))) < 1e-12

def test_rolling_ir_constant_ic():
    ic = pd.Series([2.0] * 5, index=pd.date_range("2026-01-01", periods=5))
    out = compute_rolling_ir(ic, window=3)
    assert np.isinf(out.iloc[-1])
```

**Step 2: 跑测试** → FAIL。

**Step 3: 实现**
```python
def compute_rolling_ir(ic_series, window, min_periods=None):
    """滚动窗口 IR = mean/std（ddof=1）；std=0 时 inf。"""
    if window < 1:
        raise ValueError("window 必须 >= 1")
    min_periods = window if min_periods is None else min_periods
    mean = ic_series.rolling(window=window, min_periods=min_periods).mean()
    std = ic_series.rolling(window=window, min_periods=min_periods).std(ddof=1)
    return mean / std  # std=0 → inf，与 compute_ir 语义一致
```

**Step 4: 跑测试** → PASS。

**Step 5: Commit**：`feat(factors): compute_rolling_ir`

### Task 1.3：compute_rolling_tstat

**Step 1: 写失败测试**：t = IR × √n（n = 窗口内有效样本数，非窗口长度）——用含 NaN 的窗口验证 n 取有效数。
```python
def test_rolling_tstat():
    ic = pd.Series([1.0, 2.0, np.nan, 4.0], index=pd.date_range("2026-01-01", periods=4))
    out = compute_rolling_tstat(ic, window=3)
    # 窗口 [2.0, NaN, 4.0]：mean=3.0, std=sqrt(2), n=2 → t = 3.0/sqrt(2)*sqrt(2) = 3.0
    assert abs(out.iloc[-1] - 3.0) < 1e-12
```

**Step 2: 跑测试** → FAIL。

**Step 3: 实现**：n 用 `ic_series.rolling(window).count()`；`tstat = ir * np.sqrt(n)`（n<2 时 NaN）。

**Step 4: 跑测试** → PASS。

**Step 5: Commit**：`feat(factors): compute_rolling_tstat`

---

## Task 2：analysis/factor_monitor.py（TDD）

> 只依赖 `factors.registry` + `factors.evaluation`；不依赖 backtest/strategies/portfolio/risk。

### Task 2.1：状态机纯函数

**Files:**
- Create: `tests/analysis/test_factor_monitor.py`（或 `tests/test_factor_monitor.py`）
- Create: `src/analysis/factor_monitor.py`

**Step 1: 写失败测试**
```python
def test_state_machine_transitions():
    # t 序列：+3 持续 25 日 → active；掉到 +1.5 持续 25 日 → decaying；掉到 +0.5 持续 25 日 → dead
    t_series = pd.Series([3.0]*25 + [1.5]*25 + [0.5]*25)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert states.iloc[24] == "active"
    assert states.iloc[25] == "active"      # 候选 decaying 但未满 20 日 → 维持
    assert states.iloc[49] == "decaying"
    assert states.iloc[74] == "dead"

def test_state_machine_reverse():
    t_series = pd.Series([-3.0]*25)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert states.iloc[-1] == "reverse"
```

**Step 2: 跑测试** → FAIL。

**Step 3: 实现** `run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20) -> pd.Series`：
- 候选状态：t ≥ t_active → active；t_decay ≤ t < t_active → decaying；t < t_decay → dead；t ≤ -t_active → reverse（优先级高于 active 分支的负侧）
- 防抖：候选状态连续 ≥ min_sustain 才切换，否则维持原状态、累计候选天数
- 冷启动：首日即按候选状态初始化（无历史）

**Step 4: 跑测试** → PASS。

**Step 5: Commit**：`feat(analysis): 因子状态机纯函数`

### Task 2.2：持久化（state.parquet / changes.parquet）

**Step 1: 写失败测试**
```python
def test_persistence_append_and_diff(tmp_path):
    # 首次写入 N 行 → 追加 M 行 → state.parquet 共 N+M 行无重复 (date,factor,fwd_window)
    # changes.parquet 只记录状态切换行
def test_state_schema():
    # 列: date/factor/fwd_window/ic/rolling_ic/rolling_ir/t_stat/state/sustain_days
    # dtype: date=datetime64, state=str
```

**Step 2: 跑测试** → FAIL。

**Step 3: 实现** `save_state(df, path)` / `load_state(path)` / `save_changes(df, path)`：parquet 读写 + 追加去重（`drop_duplicates(subset=[date,factor,fwd_window], keep="last")`）+ 旧快照备份。

**Step 4: 跑测试** → PASS。

**Step 5: Commit**：`feat(analysis): 状态持久化（state/changes parquet）`

### Task 2.3：编排（全因子 + 尾部增量 + 全量）

**Step 1: 写管道测试** `tests_pipeline/test_factor_monitor.py`（先写）：
- 合成行情"前 1 年截面 alpha 显著、后 1 年 alpha=0"（复用 `notebooks/icir_factor_screening.py` 的 `make_synthetic_ohlcv` 思路，beta 前段 > 0、后段 = 0），断言 `run_monitor()` 输出中因子状态在预期日期 active → decaying → dead
- 多因子独立：两个不同 alpha 的因子状态互不影响
- 增量：第二次运行（尾部增量）结果与 `full=True` 一致；state.parquet 追加无重复
- 动态发现：`run_monitor()` 缺省用 `list_factors(kind="single")` 全部（断言输出包含注册因子）

**Step 2: 跑测试** → `pytest tests_pipeline/ -v`，预期 FAIL。

**Step 3: 实现** `run_monitor(factor_names=None, price_df, fwd_windows=(5,), window=60, min_sustain=20, ..., output_dir, full=False)`：
- 因子值：`factors.registry.run_factor`（带磁盘缓存）
- forward return / IC / 滚动统计：`factors.evaluation` 链
- 尾部增量：读 state.parquet 取 `last_date` → 只重算 `last_date - window - lookback_max` 之后 → 拼接覆盖尾部重叠段
- 状态：`run_state_machine` 逐 (factor, fwd_window) 应用

**Step 4: 跑测试** → 预期 PASS（`pytest tests_pipeline/` 全绿）。

**Step 5: Commit**：`feat(analysis): run_monitor 编排（动态发现 + 尾部增量）`

---

## Task 3：yq factor monitor CLI

### Task 3.1：子命令 + 参数解析

**Files:** 参考 `src/yq/` 现有 `factor` 组（list/run/evaluate 已有）扩展 `monitor` 子命令。
- 参数：`--data`（必填）、`--factor`（可重复）、`--windows`（默认 5）、`--window`（默认 60）、`--min-sustain`（20）、`--min-obs`（5）、`--t-active`（2.0）、`--t-decay`（1.0）、`--ir-active-line`（0.7）、`--ir-dead-line`（0.3）、`--full`、`--no-cache`、`--output-dir`（默认 `data/audit/factor_monitor/`）

**Step 1: 写测试**（CLI 层）：参数解析 + 缺 `--data` 报错。
**Step 2:** FAIL → **Step 3:** 实现 → **Step 4:** PASS → **Step 5: Commit**：`feat(cli): yq factor monitor 子命令`

### Task 3.2：输出状态表 + 变更 diff

- 状态表：每 `(factor, fwd_window)` 一行（状态/当前 t/IR/最近切换日期/持续天数），按状态排序（dead 置顶）
- 变更 diff：本次运行 `changes.parquet` 新增行的人类可读输出
- 图路径：Task 4 完成后输出

**Step 1: 写测试** → 构造 monitor 结果，断言表格结构与 diff 内容 → FAIL → 实现 → PASS → **Commit**：`feat(cli): monitor 输出状态表与 diff`

### Task 3.3：端到端验证

```bash
.venv/bin/python -m yq factor monitor \
  --data data/clean/full_market_ohlcv.parquet \
  --factor calc_hv --windows 5 --window 60
```
预期：正常输出状态表 + 图路径；对 4999 股 × 近 3 年运行完成（首跑含因子值计算，分钟级）。
**Commit**：`test(cli): monitor 端到端`

---

## Task 4：analysis/plot.py 绘图

### Task 4.1：plot_factor_lifecycle

- 双轴：左轴滚动 IR（画 `--ir-active-line` 0.7 / `--ir-dead-line` 0.3 参考线），右轴 t 统计量（画 +t_active/+t_decay 判定线）
- 背景色带：按状态着色（active 绿 / decaying 黄 / dead 红 / reverse 灰蓝）
- 输入 `(date, rolling_ir, t_stat, state)` 长表切片；输出 `plt.Figure`

**测试**：`tests/analysis/test_plot.py`——smoke 测试（构造小表调用，断言返回 Figure、不抛错）；无状态转换时只画参考线。
**Commit**：`feat(analysis): plot_factor_lifecycle 双轴时序图`

### Task 4.2：plot_factor_health_heatmap

- x=时间、y=因子（或 factor×fwd_window），颜色=滚动 IR（RdYlGn，对称截断，参考 `analysis/plot.py` 既有 `plot_sweep_heatmap` 的 vmin/vmax 处理）
**测试**：smoke 测试（构造多因子小表 → Figure）。
**Commit**：`feat(analysis): plot_factor_health_heatmap`

---

## Task 5：文档契约更新（按项目重构规范）

**Files:** `docs/data-schemas.md` / `docs/project-plan.md` / `docs/history.md`
- `data-schemas.md`：+ 滚动评估输出 schema（rolling_ic/rolling_ir/t_stat）、monitor state/changes schema
- `project-plan.md`：模块状态表 + `analysis/factor_monitor` 行
- `history.md`：决策记录（2026-08-05 因子生命周期监控：设计、数据修复、实现）
**Commit**：`docs: 同步 factor monitor 契约与模块状态`

---

## Task 6：全量首跑 + 阈值校准（数据已就绪）

**Step 1:** 全量首跑（全部 single 因子，fwd_window=5，window=60）：
```bash
.venv/bin/python -m yq factor monitor --data data/clean/full_market_ohlcv.parquet --full
```

**Step 2:** 阈值校准：输出全因子滚动 IR / t 分布，对照 0.7/0.3 参考线与 t=2/1 判定线位置——若 0.7 几乎无因子达到或 0.3 几乎全部低于，按分布调整 `--ir-*-line` 与 `--t-*`（记录调整依据）。

**Step 3:** 结果写入 `docs/history.md`（各因子当前状态、阈值校准结论）。

**Commit**：`docs: 因子生命周期监控首跑结果与阈值校准`
