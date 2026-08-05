# yoyo-quant 基础设施补强 To Do

> 本清单基于 2026-06 基础设施评估（见会话结论），对 src/ 全模块逐文件核实后整理。
> 问题按优先级编号：P0 = 影响数据正确性/架构稳定性，P1 = 影响基础设施完备度，P2 = 工程加固与测试补强。
> 每个问题描述四要素：**位置 / 现状 / 影响 / 期望效果**。不含具体实现方案。
> **实施顺序说明**：execution（P1-06）由用户指定最后实施——它属于实盘模块，优先级按重要性排在此处，但实施排期在全部其余问题之后。
> **完成状态**：P0-02 已于 2026-06 完成（见 `history.md` Phase 18）。P1-01 已于 2026-06 完成（见 `history.md` Phase 19）。

## 优先级总览

| 编号 | 问题 | 所属模块 | 优先级 |
|------|------|----------|--------|
| P0-01 | 行情无复权处理 | data | P0 |
| P0-02 | 管道编排重复 4 处，无统一 orchestrator | backtest/config | P0 | ✅ 已完成 |
| P1-01 | 无交易日历 | data | P1 | ✅ 已完成 |
| P1-02 | 无增量更新，缓存不校验覆盖区间 | data | P1 |
| P1-03 | 无数据版本管理与质量校验 | data | P1 |
| P1-04 | 24 个已实现因子未注册，因子无存储/缓存 | factors | P1 |
| P1-05 | 无 IC/IR 因子评估设施 | factors | P1 |
| P1-06 | execution 模块完全缺失（用户指定最后做） | execution | P1 |
| P2-01 | 策略输出无运行时校验 | strategies | P2 |
| P2-02 | 因子无去极值/截面标准化/缺失值处理，中性化仅 demean | factors | P2 |
| P2-03 | 风控逻辑双轨：止损止盈在 BacktestEngine，与 risk 层边界模糊 | backtest/risk | P2 |
| P2-04 | 闲置与重复代码：adapter 旁路、_to_ts_code 三处重复、fetch_index_daily 半成品 | data/backtest | P2 |
| P2-05 | 测试缺口：无端到端、5 个已注册策略零测试 | tests | P2 |
| P2-06 | 集成测试过薄（仅 data/fetcher） | tests_integration | P2 |
| P2-07 | 文档数字过时（README/ project-plan） | docs | P2 |
| P2-08 | visualization 仅 3 个静态图，无交互/导出 | visualization | P2 |

---

## P0 — 数据正确性与架构稳定性

### P0-01 行情无复权处理

- **位置**：`src/data/fetcher.py` `fetch_daily`（:24）、`fetch_index_daily`（:80）
- **现状**：直接调 tushare `daily`/`index_daily` 原始价，未取 `adj_factor`，未使用 qfq/hfq 复权；全 src 无 `adj_factor|qfq|hfq|复权` 业务命中。`docs/data-schemas.md` 的 OHLCV 契约也未声明复权口径。
- **影响**：分红除权造成价格跳空，直接扭曲动量、均值回归、波动率、VWAP 等全部价格类因子；回测收益率在除权日出现虚假缺口，属于数据正确性硬伤。
- **期望效果**：数据层提供明确的复权能力（前复权/后复权），OHLCV 契约声明复权口径；因子计算路径使用复权价，回测中无除权伪信号。

### P0-02 管道编排重复 4 处，无统一 orchestrator —— ✅ **已完成（2026-06，见 history.md Phase 18）**

- **位置**：`src/backtest/pipeline.py`（新增）；迁移后的调用方 `src/backtest/walk_forward.py`、`src/backtest/continuous.py`、`src/analysis/param_sweep.py`、`src/analysis/pool_matrix.py`
- **现状（已修复）**：原 4 处各自手写；现已收敛为 `build_positions` / `run_backtest` / `run_pipeline` 三个公开函数，`walk_forward`/`continuous`/`param_sweep`/`pool_matrix` 全部复用。multi_silo 合并后段因输入已是 positions 保留两行 cap/limit API 调用（engine 已收敛到 `run_backtest`）。
- **影响（已消除）**：修改任一环节契约（如新增风控规则、改仓位 schema）必须同步 4 处，极易漏改导致各入口行为漂移；这是当前基础设施最大的维护隐患。
- **期望效果（已达成）**：存在单一管道编排入口（输入信号/参数 → 输出回测结果），4 处调用方复用同一实现；新增环节只需改动一处。新增测试 17 个，全量 897 tests 通过。

---

## P1 — 基础设施完备度

### P1-01 无交易日历 —— ✅ **已完成（2026-06，见 history.md Phase 19）**

- **位置**：`src/data/trade_calendar.py`（新增）；消费方 `src/data/earnings.py` `build_earnings_panel`（:374）、`src/data/fundamentals_quarterly.py` `build_quality_panel`（:164）——两者的 `trade_dates` 由调用方传入
- **现状（已修复）**：新增权威交易日历接口 `fetch_trade_calendar` / `fetch_trade_dates` / `is_trading_day`（tushare `trade_cal`，parquet 缓存于 `data/raw/trade_cal/{exchange}.parquet`，一次全量 [1990-01-01, 2030-12-31]）；9 个 PIT 面板消费方（notebooks 中 8 处 earnings panel + 1 处 earnings/quality panel）已从 `data["date"].unique()` 推断改为 `fetch_trade_dates(START_DATE, END_DATE)`。
- **影响（已消除）**：PIT 面板网格按真实交易日对齐，停牌日/节假日不再产生错误网格；"今天是否交易日"等基础设施判断可用 `is_trading_day`。
- **期望效果（已达成）**：数据层提供权威交易日历接口；回测引擎与 walk-forward 切分逻辑保持不变（用户确认的最小范围），仍以实际行情日期为准。新增 19 个单元测试，单元 890 + 管道 26 = 916 tests 通过（集成测试因 TUSHARE_TOKEN 过期无法运行）。

### P1-02 无增量更新，缓存不校验覆盖区间

- **位置**：`src/data/fetcher.py`（:156-158、:232-233、:289-290、:352-353）、`src/data/earnings.py`（:101-102、:161-162、:236-237）、`src/data/fundamentals_quarterly.py`（:66-67、:132-133）
- **现状**：全部缓存策略为"文件存在即返回"——请求更大日期范围也不重新抓取；无追加/刷新机制，只能手动删缓存。`fetch_earnings_history`（earnings.py:235）与 `fetch_fina_batch`（fundamentals_quarterly.py:131）的聚合缓存以"排序后前 5 个代码"命名，不同代码集合可能命中同一缓存读到错误数据（缓存键碰撞）。
- **影响**：数据时效性差（新增交易日无法自动补齐）；缓存键碰撞属于潜在静默数据错误。
- **期望效果**：缓存携带覆盖区间元数据，请求超出区间时自动增量补抓；缓存键对代码集合唯一，无碰撞可能。

### P1-03 无数据版本管理与质量校验

- **位置**：`src/data/__init__.py` `validate_ohlcv`（:11）、`src/data/storage.py`（:6-27）、全部 fetch 函数的空返回路径
- **现状**：`validate_ohlcv` 只校验列名存在，无类型/空值/非负校验；fetch 函数对空返回静默返回空 DataFrame，无告警；parquet 文件无抓取时间戳、无 schema 版本、无 manifest。
- **影响**：上游数据损坏或抓取失败时静默传入空/坏数据，错误在因子与回测阶段才暴露，难定位；无法区分"数据是旧的"还是"数据是正确的"。
- **期望效果**：有最小数据质量校验（列、dtype、无 NaN、非负价、日期连续性），抓取空结果有显式告警；数据文件带版本/时间戳元数据，可追溯。

### P1-04 24 个已实现因子未注册，因子无存储/缓存

- **位置**：`src/factors/registry.py`（注册表，55 注册条目 = 32 唯一因子 + 23 别名）；未注册因子分布在 `volatility_gtja.py`（5）、`mean_reversion.py`（4）、`trend.py`（3）、`vwap.py`（2）、`volume_price.py`（4）、`volatility.py`（1）、`cointegration.py`（5，配对专用签名）
- **现状**：约 24 个已实现因子被 `src/strategies/builtin/*` 直接 import 绕过注册表（如 `trend_gtja.py:7`、`vwap_gtja.py:7`、`gtja_mean_reversion.py:10`）。`docs/project-plan.md:28` 的"46 因子"已过时。因子计算结果无任何存储/缓存设施。
- **影响**：因子不可按名统一发现/调用，注册表口径与实际实现脱节；同一因子在多个策略中重复计算。
- **期望效果**：全部通用因子进入注册表，注册表口径 = 实际可用因子集；因子计算结果可缓存复用。

### P1-05 无 IC/IR 因子评估设施

- **位置**：全 src 无；仅有的 `per_period_ir`（`src/backtest/walk_forward.py:128`）是策略 per-period Sharpe，非因子 IC；`src/context/stock_selector.py` `evaluate_factors`（:133-206）是 coverage/stability/dispersion 质量审计，也非 IC/IR。因子评估仅存在于临时 notebook 脚本（`notebooks/evaluate_new_factors.py`）
- **现状**：src 中没有任何模块计算因子暴露、因子收益率、IC、IR。
- **影响**：新增/筛选因子缺乏标准化的量化评估手段，只能靠临时脚本，评估结果不可复现、不可比较。
- **期望效果**：有可复用的因子评估工具（IC/IR、因子收益率、分层回测等），作为策略开发的标准环节。

### P1-06 execution 模块完全缺失（**用户指定最后实施**）

- **位置**：`src/execution/` 仅 0 字节 `__init__.py`；全仓库无代码 import `src.execution`；契约已定义于 `docs/data-schemas.md:113-123`（订单状态 schema：order_id/code/side/price/shares/status/timestamp）
- **现状**：无任何实现。CLAUDE.md 定义的实盘路径 `data → factors → strategies → portfolio → risk → execution → visualization` 目前只有前半段。
- **影响**：当前框架只支持"研究 + 回测"，无法将策略接入模拟盘/实盘下单。
- **期望效果**：有统一下单接口（模拟/实盘），输入目标仓位 DataFrame、输出订单状态 DataFrame，符合已定义 schema。**排期：全部其余问题完成后最后实施。**

---

## P2 — 工程加固与测试补强

### P2-01 策略输出无运行时校验

- **位置**：`src/strategies/base.py` `Strategy.generate_signal`（:20-38）
- **现状**：返回格式（date/code/signal/confidence、signal ∈ {-1,0,1}、dtype、行序）仅存在于 docstring，无任何运行时校验。`WeightedVoteCombiner`（`combiner.py:40-44`）只校验行数一致。
- **影响**：策略实现错误（缺列、signal 越界、dtype 错误）在管道深处才暴露，或静默产生错误信号。
- **期望效果**：策略输出在进入管道前通过统一校验，错误在信号层即被拦截并给出明确报错。

### P2-02 因子无去极值/截面标准化/缺失值处理，中性化仅 demean

- **位置**：全 factors 无去极值实现；标准化只有策略内私有 `_rank_normalize`（`src/strategies/builtin/multifactor.py:70-73`、`gtja_momentum.py:74`）与数据层预计算 zscore（`src/data/earnings.py:443-444`）；`src/factors/neutralize.py` 仅支持 `demean`（:8-103）
- **现状**：因子只产出 NaN 交由调用方自行处理；无 winsorize/MAD 去极值；无统一截面标准化工具；中性化无行业 dummy 回归法、无市值/风格中性化。
- **影响**：极端值污染因子排名；各策略标准化逻辑重复且不一致；中性化方法单一限制研究面。
- **期望效果**：factors 层提供标准化的去极值、截面标准化、缺失值处理工具；中性化支持至少一种回归法，可配置。

### P2-03 风控逻辑双轨：止损止盈在 BacktestEngine，与 risk 层边界模糊

- **位置**：`src/backtest/engine.py`（ATR/固定止损止盈 :250-300）；`src/backtest/engine.py` 直接访问 `DrawdownCircuitBreaker` 私有成员（`_peak`/`_drawdown_to_exposure`/`check_fast_recovery`/`dead_zone`，:229-241）；`src/backtest/engine.py:171` 直接 import `src.factors.volume_price.calc_atr`
- **现状**：risk 层只做截面过滤（可交易性/T+1/仓位），止损止盈与断路器内嵌于回测引擎；该现状来自一次有意的重构（`docs/project-plan.md:49`），但知识分散 + 鸭子类型强耦合。
- **影响**："风控"知识分散两层，实盘路径（未来 execution）无法复用回测引擎内的止损逻辑；引擎对 CB 私有成员的依赖使两者无法独立演化。
- **期望效果**：风控规则在 risk 层有统一表达（回测与实盘共享），BacktestEngine 与 CB 通过公共接口交互，不再依赖私有成员。

### P2-04 闲置与重复代码

- **位置**：
  - `src/backtest/adapter.py`（rqalpha 旁路，:11-12 空 `TYPE_CHECKING` 块；被 `src/backtest/__init__.py:1-2` 导出，未接入主管道）
  - `_to_ts_code` 在 `src/data/fetcher.py:17`、`src/data/earnings.py:65`、`src/data/fundamentals_quarterly.py:25` 三处重复定义
  - `src/data/fetcher.py` `fetch_index_daily`（:80-120）无重试退避（对比 `fetch_daily:52-66`）、无缓存，全 src 正式代码无调用
  - `src/data/universe.py` `resolve_universe_groups`（:127）把配置解析逻辑放进 data 层，职责轻微扩张
- **现状**：如上。
- **影响**：代码重复增加维护点；闲置旁路让模块边界认知混乱；半成品函数存在被误用的风险。
- **期望效果**：公共工具收敛到单一位置；闲置代码要么接入主管道要么明确标注废弃；半成品函数补齐或移除。

### P2-05 测试缺口：无端到端、5 个已注册策略零测试

- **位置**：`tests_pipeline/`（无"原始 OHLCV → factors → strategies → risk → portfolio → backtest → 指标"全链路测试；`test_pipeline_phase2.py` 的 full pipeline 测试从手工构造 signals 开始，:32-39）；`src/strategies/builtin/` 的 `gtja_mean_reversion.py`/`trend_gtja.py`/`volatility_gtja.py`/`volume_price_gtja.py`/`vwap_gtja.py` 已自动注册但零测试；对应因子 `src/factors/trend.py`/`vwap.py`/`volatility_gtja.py` 也无直接测试；`src/strategies/reversed.py`、`src/risk/rule_registry.py` 无测试
- **现状**：约 854 单元 / 26 管道 / 8 集成测试，但如上缺口存在。
- **影响**：已注册策略无测试，改坏不会立即被发现；模块间契约只在局部验证，没有全链路保障。
- **期望效果**：有覆盖 data→backtest 全链路的管道测试；所有已注册策略与因子有最小接口测试。

### P2-06 集成测试过薄

- **位置**：`tests_integration/` 仅 `data/test_fetcher_integration.py`（约 8 个用例，只覆盖 data/fetcher；深市 000001 + 沪市 600519 各一只）
- **现状**：无任何真实 backtest/策略运行；无更广股票池覆盖。
- **影响**：真实 API 数据变化（列名、类型、新字段）无法在 CI 中捕获；多市场/多股票的真实数据正确性缺乏背书。
- **期望效果**：集成测试覆盖行情/基本面真实获取 + 至少一次真实数据驱动的回测冒烟；无 token 自动跳过机制保持。

### P2-07 文档数字过时

- **位置**：`README.md`（:16/184/204 写 "685 个测试"）、`docs/project-plan.md`（:28 "46 因子"、:81 "854 tests"）、README 目录/能力描述与 `src/` 实际不符（如 execution 未标注）
- **现状**：实际测试约 888（单元 854 + 管道 26 + 集成 8），注册因子 55 条目（32 唯一 + 23 别名），且仍在增长。
- **影响**：文档数字与代码脱节，误导评估与交接。
- **期望效果**：README/project-plan 的数字与结构描述与代码同步，或改为自动生成/指向单一事实来源。

### P2-08 visualization 仅 3 个静态图

- **位置**：`src/visualization/charts.py`（`plot_equity_curve` :10、`plot_drawdown` :42、`plot_backtest_summary` :74）
- **现状**：仅返回 matplotlib Figure，无交互（hover/缩放）、无导出封装、无报告生成。
- **期望效果**：满足"回测结果可视化 + 导出"的最小闭环（至少统一导出接口），交互能力按需扩展。
