# 因子清洗与组合流水线设计（Phase A/B/C 讨论稿）

- 日期：2026-08-05
- 状态：**讨论稿，未实施**（用户要求先出设计说明，不写代码）
- 前置：因子生命周期监控已上线（`factor-lifecycle-monitor-design.md`，Task 0-6 完成）
- 范围：把"单因子有效性监控"升级为"因子组合流水线"：筛选 → 相关性去冗余 → OOS 验证 → 合成信号

## 1. 背景与动机

全量首跑（80 个量价因子 × 全市场 3 年）发现一个值得警惕的结果：

- **active 因子只有 8 个，且全部集中在 GTJA"价格-成交量相关"类**：

| 因子 | t_stat | 连续活跃天数 |
|------|--------|------|
| calc_close_vol_rank_cov_5d / gtja_99 | +4.49 | 613 |
| calc_high_vol_rank_corr_3d / gtja_32 | +4.10 | 639 |
| calc_vwap_vol_rank_corr_5d / gtja_90 | +4.00 | 639 |
| calc_vol_rank_intraday_corr_6d / gtja_1 | +1.84 | 377 |

- 这 4 个（8 行含别名）因子的 t 与持续天数高度同步——它们本质是**同一个信号（价格与成交量的 rank 相关/协变）在不同窗口下的写法**，数学上高度共线。
- **单因子有效性 ≠ 组合有效性**：把这 4 个"一起用"，等于把同一笔赌注放大 4 倍。回测表现越好越可疑（对过拟合信号而言，样本内相关越高，回测越好看）。
- 当前监控系统只回答了"每个因子自己是否还活着"，**没有回答"哪些因子构成一个真正分散的组合"**。

这是本设计的出发点：单因子监控是地基，但真正形成可用因子组合还需要两层——**因子间相关性检查（去冗余）**与**OOS（样本外）验证**。

## 2. 问题定义

| # | 问题 | 现状 | 风险 |
|---|------|------|------|
| P1 | 因子高度相关 | 80 个量价因子中，active 的几乎全是"量价相关类"同一信号 | 组合 = 信号放大，虚假的"多因子分散"，过拟合 |
| P2 | 单因子有效 ≠ 组合有效 | 无因子间相关性矩阵/聚类/去冗余 | 选因子靠"看起来都有效"，无结构性依据 |
| P3 | 无 OOS 验证 | 滚动统计是"在线自适应"，非严格 train/test | "测出的有效因子是否可信"无法回答；选择机制可能过拟合 |
| P4 | 多重检验 | 80 个因子里纯随机也有 ~4 个 \|t\|>2（5% × 80） | 显著因子可能是噪声 |

目标：建立三层流水线——

```
① 单因子有效性筛选（滚动 IC/IR/t + 状态机）        ✅ 已交付
② 因子相关性 → 聚类去冗余（每簇留代表）            ❌ Phase A
③ walk-forward OOS 验证（train 选 → test 验证）    ❌ Phase B
④ 合成信号接入策略/组合管线                        ❌ Phase C
```

## 3. 与现有架构的关系

### 3.1 数据流位置

```
data → factors → strategies → portfolio → risk → backtest
                        ↑
              analysis/factor_monitor（已交付：滚动统计 + 状态机 + state 长表）
                        ↑
        analysis/factor_clean（本设计新增，Phase A/B/C 编排层）
```

- 本设计的**操作能力**落在 `factors/ops/`（因子清洗属于对因子的操作），**业务编排**落在 analysis 层（沿用 factor_monitor 的定位）；**不新增数据源**。
- 前置：**Phase 0 先重构 `src/factors/` 目录分层**（见 §3.4），否则 A/B/C 的新代码又要再挪一次。
- 与 `factor_monitor` 的关系：monitor 输出 state 长表（`(date, factor, fwd_window, ic, rolling_ic, rolling_ir, t_stat, state, sustain_days)`）与因子值缓存，本设计**只读**这些产物做二次加工。

### 3.2 依赖与复用（新增代码只依赖这些既有模块）

| 复用 | 位置 | 用途 |
|------|------|------|
| 因子动态发现 | `factors.registry.list_factors(kind="single")` | 枚举候选因子（含跳过缺列机制） |
| 因子值计算 + 磁盘缓存 | `factors.registry.run_factor` | 取因子值序列（算截面相关用） |
| IC/滚动统计 | `factors.ops.evaluation.compute_ic / compute_rolling_*` | 单因子统计（已交付） |
| 市场状态标注 | data 层 `limit_up / limit_down / is_suspended` | OOS 组合验证的可交易性约束 |
| train/test 窗口 | `backtest.walk_forward.generate_windows` | Phase B 的滑窗切分（**仅复用窗口生成**，不与回测逻辑耦合） |
| 绘图 | `analysis.plot`（既有 plot_sweep_heatmap / plot_factor_health_heatmap 风格） | 相关矩阵热力图、聚类树状图 |

### 3.3 边界（不做什么 / 允许什么）

- 不引入新数据（不需要新增因子、基本面、分钟数据）
- **允许** PCA / 正交化主成分——约束条件是输入因子须有合理的经济/金融解释，正交化仅作组合技术；默认路径仍是可解释的聚类去冗余（§4），正交化作为可选增强
- 不改 `strategies/` 的既有契约；Phase C 只做"合成信号"输出，接入策略层由既有 `Strategy` 框架承接
- 不做实盘执行（execution 模块仍在项目路线图）

### 3.4 Phase 0：src/factors/ 目录分层重构

**动机**：factors 目录扁平化，因子 / 算子 / 元功能（评估、中性化、缓存、调度）混杂同一层。重构后每层只依赖下层，可读性与模块边界清晰，且 Phase A/B/C 的清洗操作有明确归属。

**目标结构**：

```
src/factors/
├── __init__.py          # 顶层导出（保持旧 import 兼容）
├── registry.py          # 注册表 + 动态发现 + run_factor（调度入口，留顶层）
├── operators.py         # GTJA 算子原语（留顶层，被所有因子依赖）
├── builtin/             # 因子实现（13 个文件，只依赖 operators + pandas；
│   │                    #   命名对齐 strategies/builtin/ 先例）
│   ├── momentum.py  volume_price_gtja.py  volatility_gtja.py
│   ├── mean_reversion.py  trend.py  vwap.py  volatility.py  volume_price.py
│   └── cointegration.py  earnings.py  value.py  quality.py  liquidity.py
└── ops/                 # 对因子的操作（依赖 registry/builtin/evaluation）
    ├── evaluation.py    # IC/IR/滚动统计/分层（现状迁入）
    ├── neutralize.py    # 截面中性化（现状迁入）
    ├── cache.py         # 磁盘缓存（现状迁入）
    ├── correlation.py   # Phase A：相关性矩阵 + 聚类去冗余（新增）
    ├── oos.py           # Phase B：walk-forward OOS + bootstrap 零分布（新增）
    └── synth.py         # Phase C：合成信号（新增）
```

**影响面（已查耦合，实测）**：
- factors 内部：19 个 `.py` = 顶层 3（__init__/registry/operators）+ builtin 13 + ops 3（evaluation/neutralize/cache）；`registry._register_defaults` 在函数内延迟 import 13 个因子文件 + 模块级 1 处 cache
- src/ 外部 import：18 个文件依赖 `factors.*`，其中 **12 个需改子模块路径**（其余 6 个只 import registry/operators，保持原位）；tests 15 个文件需改
- 兼容策略：`__init__.py` 保持**顶层 re-export**（`from factors import compute_ic` 可用）；子模块路径 import（`from factors.evaluation import X`）**全量更新**为新分层（Python 对 `from A.B import C` 不 fallback 到包属性，无法兼容）

**验收（Phase 0 实测通过）**：`from factors import compute_ic` 可用；`list_factors()` 仍 93（single 88 / pair 5）；`run_factor` 磁盘缓存按因子名 key 不受影响；全量 1058 + 30 pipeline passed；16 个文件 git rename 可追溯。

## 4. Phase A：因子相关性分析 + 去冗余

> **状态：✅ 已实施（2026-08-06）**。实现计划见 [phase-a-correlation-plan.md](phase-a-correlation-plan.md)，执行记录见 [history.md](history.md) Phase 27。本节保留为设计说明（口径/阈值/算法动机），与实现契约（data-schemas.md）一致。

### 4.1 对"什么"算相关（口径选择）

| 口径 | 算法 | 回答的问题 | 用途 |
|------|------|------------|------|
| **因子值截面 rank 相关** | 每天全市场按因子值算 spearman 秩相关，再对时间取均值 | 两个因子是否给同一批股票排同样的序 | **去冗余（主口径）** |
| IC 时序相关 | 两个因子的日频 IC 序列算 pearson 相关 | 预测信号是否同向波动 | 辅助诊断 |

**为什么去冗余用因子值相关而非 IC 相关**：组合时真正冗余的是"持仓重叠"。两个因子若每天排出的股票顺序几乎一样，不管各自哪天有效，组合都是同一笔赌注放大。IC 时序相关低反而可能是好事（交替有效 = 互补），那是组合要追求的，不是要消灭的。

### 4.2 窗口与范围

- 滚动窗口：**60 个交易日**（与 monitor 一致），相关结构会漂移，须滚动更新，不能算一次用三年
- 分析对象：仅 **active / decaying** 因子（dead/reverse 因子已被判无效，不参与组合）
- 相关阈值：默认 **|ρ| > 0.7 判定冗余**（可在 configs/factor_clean.yaml 调整，见 §9）

### 4.3 去冗余算法（可解释优先，正交化为可选增强）

1. 对 active/decaying 因子两两算滚动因子值截面相关 → 相关矩阵
2. |ρ| > 阈值 → 连边 → 层次聚类（agglomerative，ward 距离）
3. 每簇只保留**代表因子**（代表标准可配置：t_stat / IR / 综合），其余标记为"冗余别名"
4. 输出代表因子清单 + 被淘汰因子的归属簇（可审计：为什么它被淘汰，跟谁是同一簇）
5. 可选增强：对去冗余后的代表因子做 PCA/正交化合成（前提：输入因子均有经济解释，见 §3.3）

### 4.4 Phase A 输出与验收

| 产出 | 形式 | 验收标准 |
|------|------|----------|
| 相关矩阵热力图 | PNG（既有 heatmap 风格） | 直观看到"量价相关类"聚成一簇 |
| 聚类树状图 | PNG | 簇划分合理，可解释 |
| 代表因子清单 | 文本/JSON | 4 个 GTJA 相关类收敛到 ≤2 个代表 |

**预期效果**：80 个量价因子的"有效集"从 8 个收敛到 2-3 个**真正独立**的信号维度（很可能量价相关类只剩 1 个代表 + 可能 1 个反向类）。这是正常结果——"我只有 1 个有效信号"比"我有 8 个信号"诚实得多。

## 5. Phase B：walk-forward OOS 验证

### 5.1 机制

```
train 期（前 6-12 个月）               test 期（未来 1-3 个月）
┌────────────────────────┐          ┌────────────────┐
│ 滚动 IC/IR/t 选 top-K  │ ────────→ │ 验证选出的因子   │
│ + Phase A 去冗余        │          │ OOS 是否仍有效   │
└────────────────────────┘          └────────────────┘
        ←────── 按月滑窗推进 ──────→（每期记录结果）
```

每期记录：选出了哪 K 个因子、test 期它们的 IC 均值 / t 是否仍显著、胜率。最终输出 **OOS 胜率表**（每期 × 每因子）与**选择机制衰减曲线**（选出的因子 OOS 有效性随时间的变化）。

### 5.2 防泄漏四约束（OOS 的灵魂）

1. train/test 日期**严格不相交**——选因子只用 train 期内统计量（state 长表按日期切片天然支持）
2. 因子值本身无 lookahead——现有量价因子全是 rolling mean/std/rank 类，纯历史值（已满足，需在测试中固化断言）
3. forward return 只在 test 期内部计算
4. 组合验证过**可交易性约束**——涨跌停/停牌/T+1 过滤，复用 data 层状态列（`exclude_untradable` 语义）

### 5.3 多重检验修正（bootstrap 零分布）

- 每期从 80 个因子里选 top-K，**纯随机数据也会有 ~4 个因子 \|t\|>2**
- 做法：把因子值随机打乱 N 次（如 200 次），得到纯随机下 t 统计量的零分布
- 只有显著性强于零分布基线的因子才允许入选（或把零分布分位数画成图上的参考线）

### 5.4 Phase B 输出与验收

| 产出 | 形式 | 验收标准 |
|------|------|----------|
| OOS 胜率表 | 长表/文本 | 每期 train 选出因子在 test 期的 IC/t 记录 |
| 选择机制衰减曲线 | PNG | 直观看到机制是否稳定 |
| bootstrap 零分布基线 | PNG + 数值 | 入选因子显著性 > 随机基线 |

**预期效果**：回答"这套选因子方法是否可信"。若 OOS 胜率 ≈ 50%，说明选择机制没有信息，回到 Phase A 重新思考；若稳定 > 60-70%，说明机制可用。**注意：OOS 验证的是"选择机制"，不是"因子永生"**——A 股 3 年只有一个市场周期，OOS 通过 ≠ 未来有效，所以监控（在线状态机）仍要持续跑，二者配套：OOS 校准方法，监控跟踪实时状态。

## 6. Phase C：合成信号接入策略层

- 去冗余后的代表因子（Phase A 输出）按**等权**或 **IC 加权**合成单一信号（默认等权，可在 configs/factor_clean.yaml 调整，见 §9）；可选增强：正交化加权（见 §3.3）
- 合成信号输出为 strategies 模块输入格式（date, code, signal, confidence），由既有 `Strategy` 框架/组合器承接
- 回测验证：接入既有 `backtest` 管道（data → factors → strategies → portfolio → risk → backtest），与"单因子最佳"对比——**验证组合是否真正优于单因子**（若组合 Sharpe 不比最佳单因子高，说明冗余没去干净或合成无效）
- 注意：Phase C 不改变 strategies/portfolio 模块本身，只新增"因子 → 合成信号"的转换层

**预期效果**：得到 1 个可交易的合成信号，其回测表现与最佳单因子相当或更好，且持仓分散度真实（不是同一批股票）。

## 7. 总体预期效果（一句话版）

> 从"80 个因子逐个看死活"升级为"**2-3 个独立信号维度 + 有据可依的选择机制 + OOS 验证过的合成信号**"，回答"我到底能用什么、为什么能用"。

## 8. 实施节奏（敏捷 + TDD，阶段交付）

| Phase | 内容 | 相对工作量 | 前置 | 状态 |
|-------|------|-----------|------|------|
| 0 | factors 目录分层重构（§3.4） | 中 | 无 | ✅ 已完成（history Phase 26） |
| A | 相关性矩阵 + 聚类去冗余（`factors/ops/correlation.py`） | 小 | 0（新代码直接落在新分层） | ✅ 已完成（history Phase 27） |
| B | walk-forward OOS + bootstrap（`factors/ops/oos.py`） | 中 | A（选因子需去冗余后的候选集） | ❌ 待做 |
| C | 合成信号 + 回测对比（`factors/ops/synth.py`） | 中 | A + B | ❌ 待做 |

- **ABC 全做**（用户已确认）；每个 Phase 独立交付、独立验收，可暂停
- 每个 Phase 按项目规范 TDD：先写测试 → 最小实现 → 跑绿 → 更新契约文档（data-schemas / project-plan / history）
- 每个 Phase 的交付标准在实现计划（factor-clean-plan.md）中逐 task 写明：功能、测试、验收命令

## 9. 配置（configs/factor_clean.yaml，Q1-Q4 默认值）

开放问题收敛为**带默认值的配置项**，用户可随时改 yaml 调整，无需改代码：

```yaml
# Phase A 相关性去冗余（对应 Q1/Q3）
corr_threshold: 0.7        # 去冗余相关阈值（调低则更激进，保留因子更少）
corr_window: 60            # 相关滚动窗口（交易日，与 monitor 一致）
cluster_linkage: ward      # 层次聚类连接方式
representative_by: t_stat  # 簇代表选择标准：t_stat | ir | combined

# Phase B OOS 验证（对应 Q2）
oos_train_months: 12       # train 期长度（月）
oos_test_months: 1         # test 期长度（月，贴合日频换仓节奏）
top_k: 5                   # 每期从去冗余候选集中选入因子数
bootstrap_iters: 200       # 零分布模拟次数（多重检验修正）

# Phase C 合成（对应 Q4）
synth_weighting: equal      # equal | ic_weighted（IC 加权更优但更易过拟合）

# 通用
exclude_untradable: true   # 沿用监控默认：排除涨跌停/停牌日
```

- 配置加载：`src/config/loader.py` 新增 `load_factor_clean_config`（独立于 load_config——后者强校验 strategies/risk 段，factor_clean.yaml 是独立清洗配置；缺省合并 + 参数校验，见 Phase A 实现）
- Q5（范围）已定：**ABC 全做**，顺序 Phase 0 → A → B → C

---

*本设计为讨论稿 v2，已吸收审阅意见（factors 分层重构、PCA 允许、Q1-4 配置化、ABC 全做）。批准后按项目规范（CLAUDE.md：TDD、模块解耦、重构五步）拆分为具体实现计划（factor-clean-plan.md），更新 data-schemas.md / project-plan.md / history.md。*
