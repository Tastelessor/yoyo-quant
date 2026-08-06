# 因子清洗（factors-clean）实现计划 —— Phase 0：src/factors/ 目录分层重构

> **For Hermes:** 按 task 逐个实现；每 task 走完整 TDD 循环（写失败测试 → 跑失败 → 最小实现 → 跑通过 → commit），实现前 invoke `karpathy-guidelines` skill。

**Goal:** 把扁平化的 `src/factors/`（19 个文件混三层）重构为分层结构：顶层只留调度（registry）与算子原语（operators），因子实现进 `factors/builtin/`，对因子的操作（评估/中性化/缓存 + 后续 A/B/C 清洗）进 `factors/ops/`。**纯结构迁移，零行为变更**。

**Architecture:** 每层只依赖下层，无反向依赖：
```
src/factors/
├── __init__.py          # 顶层 re-export（保持 from factors import X 可用）
├── registry.py          # 注册表 + 动态发现 + run_factor（调度入口，留顶层）
├── operators.py         # GTJA 算子原语（留顶层）
├── builtin/             # 13 个因子实现（只依赖 operators + pandas）
└── ops/                 # 3 个操作层（evaluation / neutralize / cache 迁入；
                         #   Phase A/B/C 的 correlation/oos/synth 后续落这里）
```

**Tech Stack:** Python 3.11+ / pytest（全量回归 1011 单测 + 26 pipeline 为基线）/ ruff。

**前置状态：**
- 设计文档 `docs/factors-clean.md` v2（§3.4，commit `ec2bb1c`）
- 工作区干净；`src/factors/` 共 19 个 `.py`：`__init__ / registry / operators`（顶层）+ 13 个因子实现 + `evaluation / neutralize / cache`（操作层）

---

## 影响面清单（已查耦合，Task 0.1 完成）

| 类别 | 数量 | 明细 |
|------|------|------|
| factors 内部文件 | 19 | 顶层 3 + builtin 13 + ops 3 |
| registry 内部 import | 14 处 | 模块级 `factors.cache`×1；函数内延迟 import 13 个因子文件 |
| src/ 外部 import | 18 文件 | `analysis/factor_monitor.py`、`backtest/engine.py`、`context/stock_selector.py`、`strategies/builtin/`×13、`yq/factors.py`、`yq/cache.py` |
| tests import | 17 文件 | `tests/factors/`×16 + `tests/test_evaluation_rolling.py` + `tests_pipeline/test_pipeline_data_to_risk.py` |
| 不动的模块 | 2 | `factors.registry`、`factors.operators`（外部直接 import，保持原位） |

## 替换映射（机械、无歧义）

| 旧路径 | 新路径 | 处数（src+tests） |
|--------|--------|------------------|
| `factors.evaluation` | `factors.ops.evaluation` | 3 + 2 |
| `factors.cache` | `factors.ops.cache` | 3 + 1 |
| `factors.neutralize` | `factors.ops.neutralize` | 9 + 1 |
| `factors.momentum` | `factors.builtin.momentum` | 2 + 1 |
| `factors.volume_price_gtja` | `factors.builtin.volume_price_gtja` | 1 + 1 |
| `factors.volatility_gtja` | `factors.builtin.volatility_gtja` | 1 + 0 |
| `factors.mean_reversion` | `factors.builtin.mean_reversion` | 1 + 1 |
| `factors.trend` | `factors.builtin.trend` | 1 + 0 |
| `factors.vwap` | `factors.builtin.vwap` | 1 + 0 |
| `factors.volatility` | `factors.builtin.volatility` | 2 + 2 |
| `factors.volume_price` | `factors.builtin.volume_price` | 3 + 1 |
| `factors.cointegration` | `factors.builtin.cointegration` | 2 + 1 |
| `factors.earnings` | `factors.builtin.earnings` | 2 + 1 |
| `factors.value` | `factors.builtin.value` | 2 + 1 |
| `factors.quality` | `factors.builtin.quality` | 2 + 1 |
| `factors.liquidity` | `factors.builtin.liquidity` | 2 + 1 |

## 关键技术事实（决定做法，勿偏离）

1. **`from factors.evaluation import X` 无法靠 `__init__.py` 属性兼容**：CPython 对 `from A.B import C` 只尝试导入子模块 `A.B`，找不到即 `ModuleNotFoundError`，不会 fallback 到包属性。→ 所有子模块路径 import 必须**全量替换**；`__init__.py` 只保证 `from factors import compute_ic` 这类顶层 re-export 不破。
2. **磁盘缓存不失效**：`run_factor` 的缓存 key 按因子名（非模块路径），迁移后命中不变。
3. **行为不变锚点**：`list_factors()` 仍 93 条目（single 88 / pair 5）；`import factors; factors.compute_ic / calc_hv` 可用。
4. **git mv 保留历史**：用 `git mv` 而非 `mv`，git 的 rename 检测使 diff 干净。
5. **中间态允许红**：Task 2 迁移后旧 import 全部断裂（预期），逐 task 修复，Task 4 之后全量绿。

---

## Task 1：分层卫生测试（失败先行）

**Objective:** 建立"新分层结构存在 + 顶层 re-export 不破"的回归锚点。

**Files:**
- Add: `tests/factors/test_layering.py`

**Step 1: 写测试**（新路径尚不存在，必然红）

```python
"""factors 分层卫生测试：顶层(registry/operators) + builtin(因子实现) + ops(操作)。"""
import importlib

BUILTIN = [
    "momentum", "volume_price_gtja", "volatility_gtja", "mean_reversion",
    "trend", "vwap", "volatility", "volume_price", "cointegration",
    "earnings", "value", "quality", "liquidity",
]
OPS = ["evaluation", "neutralize", "cache"]


def test_builtin_modules_importable():
    for m in BUILTIN:
        importlib.import_module(f"factors.builtin.{m}")


def test_ops_modules_importable():
    for m in OPS:
        importlib.import_module(f"factors.ops.{m}")


def test_top_level_modules_importable():
    for m in ["registry", "operators"]:
        importlib.import_module(f"factors.{m}")


def test_top_level_reexports_work():
    from factors import (  # noqa: F401
        calc_hv,
        calc_momentum_5d_change,
        compute_ic,
        list_factors,
        neutralize_factors,
    )
```

**Step 2: 跑失败** — 预期 `ModuleNotFoundError: No module named 'factors.builtin'`（3 个测试红，`test_top_level_reexports_work` 绿）

```bash
.venv/bin/python -m pytest tests/factors/test_layering.py -q
```

**Step 3: 最小实现** — 本 task 不改代码，红即通过（证明"重构尚未发生"）

**Step 4: 跑通过** — 留到 Task 2/3 迁移后转绿

**Step 5: commit** — `feat(tests): 分层卫生测试锚点（factors builtin/ops 结构）`

---

## Task 2：git mv 迁移 16 个文件

**Objective:** 13 个因子实现 → `factors/builtin/`，3 个操作层 → `factors/ops/`。

**Files:**
- Move: 13 个因子文件 + `evaluation.py / neutralize.py / cache.py`

**Step 1: 执行迁移**（一条命令，git mv）

```bash
cd /Users/erwei/.hermes/project/yoyo-quant
mkdir -p src/factors/builtin src/factors/ops
git mv src/factors/momentum.py src/factors/volume_price_gtja.py \
       src/factors/volatility_gtja.py src/factors/mean_reversion.py \
       src/factors/trend.py src/factors/vwap.py src/factors/volatility.py \
       src/factors/volume_price.py src/factors/cointegration.py \
       src/factors/earnings.py src/factors/value.py src/factors/quality.py \
       src/factors/liquidity.py src/factors/builtin/
git mv src/factors/evaluation.py src/factors/neutralize.py src/factors/cache.py src/factors/ops/
git status --short   # 应显示 16 个 renamed + 2 个新目录
```

**Step 2: 验证迁移** — `test_layering` 的 builtin/ops 部分转绿；旧路径测试红属预期

```bash
.venv/bin/python -m pytest tests/factors/test_layering.py -q
# 预期：test_builtin_modules_importable / test_ops_modules_importable 绿
#       test_top_level_reexports_work 仍红（__init__.py 未改，Task 3）
```

**Step 3: commit** — `refactor(factors): 因子实现迁入 builtin/，操作层迁入 ops/`

> 注意：此 commit 后全库测试大量红（旧 import 全断），是**预期中间态**，不要惊慌回滚；Task 3-4 修复。

---

## Task 3：重写 `__init__.py` + 修正 registry.py 内部 import

**Objective:** 顶层 re-export 指向新路径；registry 内部 14 处 import 更新。

**Files:**
- Modify: `src/factors/__init__.py`（重写 import 段，`__all__` 不变）
- Modify: `src/factors/registry.py`（`factors.cache` → `factors.ops.cache`；函数内 13 个因子 → `factors.builtin.*`）

**Step 1: 修改 `src/factors/__init__.py`** — 仅替换 import 语句的前缀（内容函数名与 `__all__` 完全不动）：

```python
from factors.ops.cache import clear_factor_cache
from factors.builtin.cointegration import (...)
from factors.builtin.earnings import calc_earnings_acceleration, calc_earnings_surprise
from factors.ops.evaluation import (...)
from factors.builtin.liquidity import calc_amihud, calc_turnover
from factors.builtin.momentum import (...)
from factors.ops.neutralize import demean_by_industry, neutralize_factors
from factors.builtin.quality import (...)
from factors.registry import (...)
from factors.builtin.value import calc_bp, calc_ep
from factors.builtin.volatility import calc_hv
from factors.builtin.volume_price import calc_atr, calc_obv, calc_rsi, calc_volume_ratio
```

**Step 2: 修改 `src/factors/registry.py`** — 精确替换（模块级 + 函数内）：

```bash
# 模块级 cache
sed -i '' 's/from factors\.cache import/from factors.ops.cache import/' src/factors/registry.py
# 函数内 13 个因子文件
sed -i '' -E 's/from factors\.(momentum|volume_price_gtja|volatility_gtja|mean_reversion|trend|vwap|volatility|volume_price|cointegration|earnings|value|quality|liquidity) import/from factors.builtin.\1 import/' src/factors/registry.py
grep -n "from factors\." src/factors/registry.py   # 确认只剩 factors.ops.cache / factors.builtin.*
```

**Step 3: 验证** — registry 层恢复可用（此时 tests 旧 import 仍红，属预期）：

```bash
.venv/bin/python -c "
import factors
print('因子总数:', len(factors.list_factors()))
print('single:', len(factors.list_factors(kind='single')))
print('re-export:', factors.compute_ic, factors.calc_hv is not None)
"
# 预期：因子总数 93 / single 88 / re-export 正常
.venv/bin/python -m pytest tests/factors/test_layering.py tests/factors/test_registry.py -q
```

**Step 4: commit** — `refactor(factors): __init__ 与 registry 指向新分层`

---

## Task 4：批量替换外部 import（src 18 + tests 17）

**Objective:** 全部子模块路径 import 更新到新分层；全量测试恢复绿。

**Files:**
- Modify: src/ 外部 18 文件（排除 `src/factors/` 自身）
- Modify: tests 17 文件

**Step 1: 精确替换**（两条 sed，先 dry-run 后执行）：

```bash
cd /Users/erwei/.hermes/project/yoyo-quant
# dry-run：确认命中清单
rg -l 'from factors\.(evaluation|cache|neutralize) import' src/ tests/ tests_pipeline/ -g '*.py' -g '!src/factors/*.py'
rg -l 'from factors\.(momentum|volume_price_gtja|volatility_gtja|mean_reversion|trend|vwap|volatility|volume_price|cointegration|earnings|value|quality|liquidity) import' src/ tests/ tests_pipeline/ -g '*.py' -g '!src/factors/*.py'

# 执行
rg -l 'from factors\.(evaluation|cache|neutralize) import' src/ tests/ tests_pipeline/ -g '*.py' -g '!src/factors/*.py' \
  | xargs sed -i '' -E 's/from factors\.(evaluation|cache|neutralize) import/from factors.ops.\1 import/'
rg -l 'from factors\.(momentum|volume_price_gtja|volatility_gtja|mean_reversion|trend|vwap|volatility|volume_price|cointegration|earnings|value|quality|liquidity) import' src/ tests/ tests_pipeline/ -g '*.py' -g '!src/factors/*.py' \
  | xargs sed -i '' -E 's/from factors\.(momentum|volume_price_gtja|volatility_gtja|mean_reversion|trend|vwap|volatility|volume_price|cointegration|earnings|value|quality|liquidity) import/from factors.builtin.\1 import/'

# 确认零残留
rg -n 'from factors\.(evaluation|cache|neutralize|momentum|volume_price_gtja|volatility_gtja|mean_reversion|trend|vwap|volatility|volume_price|cointegration|earnings|value|quality|liquidity) import' src/ tests/ tests_pipeline/ -g '*.py' || echo 'OK 零残留'
```

**Step 2: 跑通过** — 全量恢复绿（基线 1011 单测 + 26 pipeline，只多不少）：

```bash
.venv/bin/python -m pytest -q 2>&1 | tail -3
.venv/bin/python -m pytest tests_pipeline/ -q 2>&1 | tail -3
.venv/bin/python -c "import factors; print(len(factors.list_factors()))"   # 93
```

**Step 3: commit** — `refactor(factors): 外部 import 全部指向新分层（builtin/ops）`

---

## Task 5：ruff + 契约文档 + 最终 commit

**Objective:** 代码规范 + 契约文档同步 + 收尾。

**Step 1: ruff 检查**（本任务改动文件，E501 等既有存量错误不在范围）：

```bash
.venv/bin/ruff check src/factors/ src/analysis/factor_monitor.py src/backtest/engine.py src/context/stock_selector.py src/strategies/builtin/ src/yq/ tests/factors/ tests/test_evaluation_rolling.py tests_pipeline/test_pipeline_data_to_risk.py
.venv/bin/ruff format --check src/factors/
```

**Step 2: 更新契约文档：**
- `docs/factors-clean.md` §3.4：修正"外部旧 import 不破"表述 → "**顶层 re-export 不破（`from factors import compute_ic`），子模块路径 import 全部更新为新分层**"（原因见"关键技术事实 1"）；builtin 数量 15 → 13
- `docs/data-schemas.md`：factors 模块引用路径更新（`factors/evaluation.py` → `factors/ops/evaluation.py` 等，若文档中出现）
- `docs/project-plan.md`：目录结构树更新为分层结构；模块状态表标注 factors 已分层
- `docs/history.md`：新增 Phase 26 决策记录（分层动机、影响面、关键技术事实、验收锚点）

**Step 3: 全量回归（最终验收）：**

```bash
.venv/bin/python -m pytest -q 2>&1 | tail -1          # ≥1011 passed
.venv/bin/python -m pytest tests_pipeline/ -q 2>&1 | tail -1   # ≥26 passed
.venv/bin/python -c "from factors import compute_ic, calc_hv; import factors.ops.evaluation, factors.builtin.momentum; print('分层 OK')"
```

**Step 4: commit** — `docs: 同步 factors 分层契约（Phase 0 完成）`

---

## 验收总纲（Phase 0 done 的定义）

1. `tests/factors/test_layering.py` 全绿（分层锚点）
2. 全量 `pytest`（tests/ + tests_pipeline/）≥ 基线 1011 + 26
3. `list_factors()` 仍 93（single 88 / pair 5），`run_factor` 缓存命中不受影响
4. `from factors import compute_ic, calc_hv` 可用；旧子模块路径 `from factors.evaluation import X` 报 `ModuleNotFoundError`（**预期**，不兼容）
5. git 历史可追溯：16 个文件显示为 renamed，非 delete+add

---

*本计划覆盖 Phase 0（factors 分层重构）。Phase A/B/C 实现计划在 Phase 0 验收后另行编写。*
