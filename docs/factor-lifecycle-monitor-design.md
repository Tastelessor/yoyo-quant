# 因子生命周期监控设计（v1）

- 日期：2026-08-05
- 状态：已获用户批准（brainstorming 流程）
- 范围：为日频交易者提供因子"活跃 / 衰减 / 失效"持续监控，支撑换因子决策

## 1. 背景与动机

- 小型游资因子有效性一般 6-18 个月；公开因子被 AI 量化抢跑后，有效窗口可能只剩 2-8 个月。
- 需要**持续监控**而非一次性筛查：定期跑、存状态、看趋势，判断"什么时候该换因子"。
- 用户经验判断值：滚动 IR 持续 > 0.7 视为活跃，< 0.3 视为失效（经验值，仅作参考线，判定用统计量，见 §5）。

## 2. 需求确认（用户逐项决策）

| 决策点 | 结论 |
|--------|------|
| 评估形态 | 持续监控优先（定期跑 + 状态存储 + 趋势/预警输出） |
| 数据范围 | 全市场近 2 年；**直接全量方案，不设 csi300 分阶段**（数据准备为前置任务，见 §10） |
| 历史长度 | 近 2 年（AI 量化时代因子衰减加速，长历史反而找不出好因子） |
| 失效判定 | 双轨：滚动 IR 0.7/0.3 仅画参考线；判定用滚动 t 统计量（|t|>2 活跃、<1 失效，连续 ≥20 交易日才切换） |
| 因子范围 | `kind="single"` 量价类，`list_factors()` 动态发现，不 hardcode |
| 实现方案 | 模块化：`factors/evaluation.py` 滚动原语 + `analysis/factor_monitor.py` + `yq factor monitor` + `analysis/plot.py` |
| 增量策略 | 默认尾部增量（每次 ~1 分钟），`--full` 全量重算留给冷启动/校准 |
| 数据准备 | 拉全市场近 2 年数据（含市场状态列）为前置任务，见 §10；监控管道开发用合成数据验证，不阻塞 |

## 3. 核心概念

- **日频截面 IC**：每个交易日对全市场截面算一次因子值与 forward return 的 spearman 相关（`compute_ic` 已有）。评估粒度 = 日频，无日内数据，与日频交易匹配。
- **滚动统计**：对日频 IC 时序做 `rolling(window)` 聚合：
  - 滚动 IC = 窗口内 IC 均值
  - 滚动 IR = 窗口内 mean / std（ddof=1）
  - 滚动 t 统计量 = IR × √n（n = 窗口内有效样本数）——显著性语义，与窗口长度解耦
- **状态机**：active / decaying / dead 三态 + reverse 参考态（见 §5）。

## 4. 架构

```
factors/evaluation.py（扩展，纯函数、无状态、不依赖交易管线与绘图）
├── compute_rolling_ic(ic_series, window, min_periods) -> pd.Series
├── compute_rolling_ir(ic_series, window, min_periods) -> pd.Series
└── compute_rolling_tstat(ic_series, window, min_periods) -> pd.Series

analysis/factor_monitor.py（新增；只依赖 factors.registry + factors.evaluation）
├── 状态机：active / decaying / dead / reverse，防抖切换
├── 持久化：state.parquet 追加 + changes.parquet diff
└── 编排：list_factors(kind="single") 动态发现 → 批量评估 → 状态判定

yq factor monitor 子命令 + 薄壳脚本
└── 参数与输出见 §8；icir_factor_screening.py 保留为一次性筛查入口

analysis/plot.py（扩展）
├── plot_factor_lifecycle(states, factor, window)    # 单因子：滚动 IR + 参考线 + t 副轴 + 状态色带
└── plot_factor_health_heatmap(states)               # 全因子 × 时间热力图（全局扫衰减）
```

**数据流**：

```
行情 parquet（日线 + 市场状态列）
  → list_factors(kind="single")                 # 动态发现全部量价因子
  → compute_forward_returns → compute_ic        # 日频截面 IC（已有）
  → rolling_ic / rolling_ir / rolling_tstat     # 新增纯函数
  → factor_monitor：状态机 + 持久化 + diff
  → yq factor monitor：状态表 + 图
```

**滚动原语位置决策**（用户关切：底层复用、业务解耦）：
- 滚动统计是"对 `compute_ic` 输出做窗口聚合"，是 `factors/evaluation.py` 的自然扩展，契约一致（纯 Series 输出、逐行对齐）。
- 不与 `backtest/walk_forward.py` 强行共用：walk_forward 是"按月切 train/test 日期窗跑回测"，与"时序窗口统计"是不同抽象层级；强行抽公共层只会引入跨模块耦合。项目无 `src/utils` 公共层，刻意保持模块独立。
- 复用发生在语义层：monitor、plot、未来预警/策略层都调用 evaluation 的纯函数；将来 walk_forward 需要嵌套滚动评估时直接 import evaluation 即可。
- 解耦保证：`analysis/factor_monitor.py` 不依赖 backtest/strategies/portfolio/risk，可独立运行。

## 5. 状态机设计

输入：每日滚动 t 统计量序列（按 `(factor, window)` 一条）。

| 状态 | 判定条件（滚动 t 统计量） | 含义 |
|------|--------------------------|------|
| active | t ≥ +2 | 预测力显著为正，可用 |
| decaying | +1 ≤ t < +2 | 减弱但仍边际 |
| dead | t < +1 | 失效 |
| reverse | t ≤ -2 | 显著为负，提示反向有效（参考，不参与主流程） |

- **防抖**：候选状态须持续 ≥ `min_sustain`（默认 20 交易日）才正式切换，否则维持原状态并累计候选持续天数。防止单周噪声误判。
- **冷启动**：首跑无历史，从首日起按规则回溯标注（历史标注仅供参考，不影响当前状态）。
- **经验值对应关系**（窗口 60 日时）：IR=0.7 ↔ t≈5.4；IR=0.3 ↔ t≈2.3。用户的 0.7/0.3 比 t=2/1 判定严格得多——阈值全部可配置，首跑后用实际分布校准（见 §11 测试里的校准步骤）。
- **参考线**：滚动 IR 0.7（活跃参考）/ 0.3（失效参考）仅画图，不参与判定。

## 6. 增量策略（第一版）

- **默认尾部增量**：状态快照 `state.parquet` 记录每因子每交易日滚动统计与状态；每次运行读快照 → 取上次覆盖日 `last_date` → 只重算 `last_date - window - 因子lookback缓冲` 之后的数据（因子值、forward return、IC、滚动统计）→ 与快照拼接（尾部重叠段覆盖，保证一致）→ 更新状态机。
- 效果：**每天跑也约 1 分钟**，失效判定近乎实时（日频交易者友好）。
- `--full` 全量重算：冷启动（首跑 2 年）与阈值校准用。
- 计算量基准（全市场 4500 股 × 500 交易日 × 88 个 single 因子）：因子值 2-7 分钟（有磁盘缓存）、IC 1-2 分钟、滚动可忽略；全量首跑约 5-10 分钟。

## 7. 持久化 schema

`data/audit/factor_monitor/` 下：

**state.parquet**（长表，`(date, factor, fwd_window)` 每行）：

| 列 | 类型 | 说明 |
|----|------|------|
| date | datetime64 | 交易日 |
| factor | str | 因子名 |
| fwd_window | int | forward return 窗口（对应 `evaluate` 的 `windows` 概念） |
| ic | float | 当日截面 IC |
| rolling_ic | float | 滚动窗口 IC 均值 |
| rolling_ir | float | 滚动 mean/std |
| t_stat | float | IR × √n |
| state | str | active/decaying/dead/reverse/none |
| sustain_days | int | 当前候选状态持续天数 |

写入：首跑全量；之后覆盖尾部重叠段 + 追加新段。重写前保留旧快照备份。

**changes.parquet**（状态变更 diff，追加式）：`factor / fwd_window / changed_on / from_state / to_state / sustain_days`。

> 命名约定：`fwd_window`（schema 列）指 forward return 窗口；CLI `--window` 指滚动统计窗口（交易日）。两者不同，勿混淆。

## 8. CLI 设计（`yq factor monitor`）

```
yq factor monitor \
  --data data/clean/csi300_ohlcv.parquet \
  [--factor NAME]...            # 缺省 = list_factors(kind="single") 全部
  [--windows 5]                 # forward return 窗口，默认 5
  [--window 60]                 # 滚动统计窗口（交易日）
  [--min-sustain 20]            # 状态切换防抖天数
  [--min-obs 5]                 # 单日截面 IC 最小样本（透传 compute_ic）
  [--t-active 2.0] [--t-decay 1.0]      # 判定阈值
  [--ir-active-line 0.7] [--ir-dead-line 0.3]  # 参考线（仅绘图）
  [--full]                      # 全量重算（默认尾部增量）
  [--no-cache]                  # 禁用因子磁盘缓存
  [--output-dir data/audit/factor_monitor/]
```

输出：
1. **当前状态表**（每 `(factor, fwd_window)` 一行：当前状态、当前 t/IR、最近切换日期、持续天数）
2. **变更 diff**（本次运行状态切换列表）
3. **图**：每因子 lifecycle 图 + 全因子健康热力图（输出到 output-dir/figures/）

## 9. 绘图输出

- `plot_factor_lifecycle`：双轴——左轴滚动 IR（画 0.7/0.3 参考线），右轴 t 统计量（画 +2/+1 判定线），背景色带按状态着色（active 绿 / decaying 黄 / dead 红）。
- `plot_factor_health_heatmap`：x=时间、y=因子（或因子×窗口），颜色=滚动 IR 或状态编码，一眼扫出全库衰减趋势。

## 10. 数据准备前置任务（全量方案，独立于监控开发，可并行）

1. **全市场近 2 年**：data 模块拉全市场日线（约 5000 股 × 500 日 ≈ 250 万行，tushare 限频需分批/节流）+ 市场状态标注 → `data/clean/full_market_ohlcv.parquet`。
2. **市场状态列必须齐备**：数据须含 `limit_up / limit_down / is_suspended` 布尔列；缺列时 `exclude_untradable` 静默失效，IC 会被涨跌停/停牌污染。若 tushare 状态字段不可用，可用价格推断（涨停 ≈ `close == round(prev_close * 1.1, 2)` 等）兜底，但需注明推断局限。
3. **开发期验证**：监控管道开发与测试用合成数据（见 §11），无需等全市场数据；全市场数据就绪后首跑即全量。

## 11. 测试计划（TDD，先写测试再实现）

**tests/test_evaluation_rolling.py**（纯函数）：
- 正常路径：手工构造 IC 序列，验证滚动 IC/IR/t 数值
- 边界：窗口不足 → NaN（min_periods 生效）、空序列
- 类型：返回 Series、index 与输入对齐
- 特殊值：std=0 时 t 统计量为 inf 的处理

**tests_pipeline/test_factor_monitor.py**（端到端）：
- 构造**前 1 年截面 alpha 显著、后 1 年 alpha=0** 的合成行情（多股票），断言状态机在预期时间点 active → decaying → dead
- 多因子独立性：一个因子失效不影响另一个
- 增量重跑：第二次运行只重算尾部，结果与全量重算一致；state.parquet 追加不重复
- 持久化 schema 正确（列、dtype）

**阈值校准（首跑后人工步骤）**：输出全因子滚动 IR / t 分布，对照 0.7/0.3 与 t=2/1 的位置，确认或调整判定阈值。

## 12. 非目标（YAGNI，二期再做）

- 不接策略层自动降权（monitor 输出结构化状态为二期留口）
- 不做预警通知（邮件/IM）
- 不做滚动 long_short 收益曲线
- 不纳入 fundamental / pair 因子
- 不改 walk_forward、不抽公共滚动层
- 不做日内数据

## 13. 文档契约更新（实现阶段执行，按项目重构规范）

- `docs/data-schemas.md`：+ 滚动评估输出 schema、monitor state/changes schema
- `docs/project-plan.md`：模块状态表 + `analysis/factor_monitor` 行
- `docs/history.md`：决策记录（2026-08-05 因子生命周期监控设计）
