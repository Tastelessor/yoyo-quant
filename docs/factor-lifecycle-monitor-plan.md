# 因子生命周期监控实现计划

- 依据：`docs/factor-lifecycle-monitor-design.md`（v1，全量方案，commit f813d16）
- 方法：绝对 TDD——每个 task 先写测试再实现；完成一个 task 后运行其测试并更新项目文档
- 实现开始前：按项目规范 invoke `karpathy-guidelines` skill

## Task 1：evaluation.py 滚动原语（TDD）

**测试** `tests/test_evaluation_rolling.py`（先写）：
- `compute_rolling_ic / compute_rolling_ir / compute_rolling_tstat` 正常路径（手工构造 IC 序列验证数值）
- 边界：窗口不足 → NaN（min_periods 生效）、空序列
- 类型：返回 Series、index 与输入对齐
- 特殊值：窗口内 std=0 时 t 统计量为 inf

**实现** `src/factors/evaluation.py` 新增三个纯函数：
- `compute_rolling_ic(ic_series, window, min_periods=None) -> pd.Series`：滚动窗口 IC 均值
- `compute_rolling_ir(ic_series, window, min_periods=None) -> pd.Series`：滚动 mean/std（ddof=1）
- `compute_rolling_tstat(ic_series, window, min_periods=None) -> pd.Series`：IR × √n（n=窗口内有效样本数）

**验收**：`pytest tests/test_evaluation_rolling.py` 全绿。

## Task 2：analysis/factor_monitor.py 状态机 + 编排 + 持久化（TDD）

**测试** `tests_pipeline/test_factor_monitor.py`（先写）：
- 构造**前 1 年截面 alpha 显著、后 1 年 alpha=0** 的合成行情（多股票多因子），断言状态机在预期时间点 active → decaying → dead 切换
- 多因子独立性：一个因子失效不影响另一个的状态
- 尾部增量重跑：第二次运行只重算尾部，结果与全量重算一致；state.parquet 追加不重复、schema（列/dtype）正确
- changes diff：状态切换记录 `factor / fwd_window / changed_on / from_state / to_state / sustain_days`

**实现** `src/analysis/factor_monitor.py`（只依赖 `factors.registry` + `factors.evaluation`）：
- 状态机：active（t≥+2）/ decaying（+1≤t<+2）/ dead（t<+1）/ reverse（t≤-2），候选状态持续 ≥ min_sustain（默认 20）才正式切换
- 编排：`list_factors(kind="single")` 动态发现 → forward returns → IC → 滚动统计 → 状态判定
- 持久化：`state.parquet`（长表：date/factor/fwd_window/ic/rolling_ic/rolling_ir/t_stat/state/sustain_days）+ `changes.parquet` 追加
- 增量：默认尾部增量（只重算 last_date - window - lookback 缓冲之后），`full=True` 全量重算

**验收**：`pytest tests_pipeline/` 全绿。

## Task 3：yq factor monitor CLI

**实现**：CLI 子命令（`src/yq/` 现有 factor 组扩展或新子命令）：
- 参数：`--data`（必填）、`--factor`（可重复，缺省=全部 single）、`--windows`（默认 5）、`--window`（默认 60）、`--min-sustain`（20）、`--min-obs`（5）、`--t-active`（2.0）、`--t-decay`（1.0）、`--ir-active-line`（0.7）、`--ir-dead-line`（0.3）、`--full`、`--no-cache`、`--output-dir`（默认 `data/audit/factor_monitor/`）
- 输出：当前状态表（每 (factor, fwd_window) 行：状态/当前 t/IR/最近切换/持续天数）+ 本次变更 diff + 图路径

**验收**：`yq factor monitor --data <合成/现有数据>` 端到端跑通，输出结构符合 §8。

## Task 4：analysis/plot.py 绘图

**实现**：
- `plot_factor_lifecycle(states, factor, fwd_window)`：双轴——左轴滚动 IR（0.7/0.3 参考线），右轴 t 统计量（+2/+1 判定线），背景色带按状态着色
- `plot_factor_health_heatmap(states)`：x=时间、y=因子，颜色=滚动 IR 或状态编码

**验收**：对 Task 2 的合成数据输出图，肉眼可辨状态切换。

## Task 5：文档契约更新（按项目重构规范）

- `docs/data-schemas.md`：+ 滚动评估输出 schema、monitor state/changes schema
- `docs/project-plan.md`：模块状态表 + `analysis/factor_monitor` 行（状态 ✅）
- `docs/history.md`：决策记录（2026-08-05 因子生命周期监控设计与实现）

**验收**：文档与实现一致，引用无遗漏。

## Task 6：全量首跑与阈值校准（数据就绪后，独立于 1-5）

- 全市场近 2 年数据（含市场状态列，见设计 §10）就绪后：`yq factor monitor --data data/clean/full_market_ohlcv.parquet --full`
- 输出全因子滚动 IR / t 分布，对照 0.7/0.3 与 t=2/1 位置，确认或调整判定阈值
- 结果记录到 `docs/history.md`
