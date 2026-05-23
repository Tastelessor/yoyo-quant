# yoyo-quant 项目计划

## 架构概览

```
                ┌→ backtest（模拟评估）
data → factors → strategies → portfolio → risk ─┤
                └→ execution（实盘/模拟盘）      ↓
                                            visualization
```

模块间通过 DataFrame schema 契约交互，单向数据流，无循环依赖。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 项目骨架 | ✅ 完成 | pyproject.toml, 目录结构, ruff/pytest 配置 |
| data schema | ✅ 完成 | validate_ohlcv + 测试通过 |
| data fetcher | ✅ 完成 | fetcher.py + 6 tests |
| data storage | ✅ 完成 | storage.py + 5 tests |
| data filters | ✅ 完成 | 涨跌停/停牌/T+1 过滤 + 11 tests |
| factors (HV) | ✅ 完成 | volatility.py + 6 tests |
| strategies (均值回归) | ✅ 完成 | mean_reversion.py + 8 tests |
| backtest (rqalpha adapter) | ✅ 完成 | adapter.py + 11 tests |
| portfolio (equal weight) | ✅ 完成 | allocator.py + 9 tests |
| risk (position limit) | ✅ 完成 | position_limit.py + 8 tests |
| backtest (lightweight engine) | ✅ 完成 | engine.py + 14 tests |
| visualization | ✅ 完成 | charts.py + 6 tests |
| execution | 🔲 未开始 | |

---

## Phase 1: 基础建设 ✅ 完成

### 目标
建立数据获取→因子计算→策略信号→rqalpha 回测的最小闭环。

### Task 1: HV 因子（TDD）✅
- [x] 写测试：`calc_hv(df, window=20)` 返回 20 日历史波动率
- [x] 实现 `src/factors/volatility.py`
- [x] 测试通过（6 tests）

### Task 2: 数据获取器（TDD）✅
- [x] 写测试：`fetch_daily(code, start, end)` 返回符合 OHLCV schema 的 DataFrame（mock akshare）
- [x] 实现 `src/data/fetcher.py`，调用 akshare `stock_zh_a_hist`
- [x] 测试通过（6 tests）

### Task 3: 数据存储（TDD）✅
- [x] 写测试：`save_parquet(df, path)` / `load_parquet(path)` 读写一致
- [x] 实现 `src/data/storage.py`
- [x] 测试通过（5 tests）

### Task 4: 均值回归策略（TDD）✅
- [x] 策略规则：价格偏离 20 日均线 ±2σ 入场，回归均线出场
- [x] 写测试：`mean_reversion信号(df) → signal DataFrame`
- [x] 实现 `src/strategies/mean_reversion.py`
- [x] 测试通过（8 tests）

### Task 5: rqalpha 最小集成 ✅
- [x] 研究 rqalpha 数据格式要求和 mod 注册方式
- [x] 写 adapter 将我们的 schema 转换为 rqalpha 兼容格式
- [x] 测试通过（11 tests，mock rqalpha）

### Task 6: 边界情况处理 ✅
- [x] 停牌/涨跌停标注 → `data.filters.detect_limit_price()` + `detect_suspension()`
- [x] 可交易性过滤 → `risk.tradability.filter_tradable()`
- [x] A 股 T+1 规则 → `risk.tradability.enforce_t1()`
- [x] 对应测试用例（11 tests，分属 data/ 和 risk/）

---

## Phase 2: 框架设计 ✅ 完成

### 目标
模块化策略框架成型，数据与可视化解耦。

### Task 1: 完善 data-schemas.md ✅
- [x] 补全 backtest 输出 schema：权益曲线（equity/cash/position_value/returns）+ 绩效指标（total_return/annual_return/sharpe_ratio/max_drawdown/win_rate/trade_count）

### Task 2: portfolio 模块（TDD）✅
- [x] `equal_weight(signals, prices, capital)` → 按信号均分仓位，股数取整到 100 手
- [x] 测试通过（9 tests）

### Task 3: risk 模块 — 仓位集中度（TDD）✅
- [x] `apply_position_limit(positions, max_weight)` → 单票权重上限，超出部分再分配
- [x] 测试通过（8 tests）

### Task 4: 轻量回测引擎（TDD）✅
- [x] `BacktestEngine(capital).run(signals, prices)` → trades + equity_curve + metrics
- [x] 支持买入/卖出信号执行，跟踪现金+持仓，计算权益曲线和绩效指标
- [x] 测试通过（14 tests）

### Task 5: visualization 模块（TDD）✅
- [x] `plot_equity_curve(eq)` — 权益曲线图（含现金和持仓区域）
- [x] `plot_drawdown(eq)` — 回撤图
- [x] `plot_backtest_summary(result)` — 组合图（权益+回撤+指标文字）
- [x] 测试通过（6 tests）

---

## Phase 3: 策略开发

### 目标
具体策略实现和回测验证。

### 待拆分
- 波动率数据分析应用（IV 均值回归、PCR 情绪指标）
- 多策略组合
- 风控体系完善
- 机器学习辅助因子挖掘（探索性）

---

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-23 | 项目计划采用 master plan + TodoWrite 执行 | 避免文件分散，保持整体可见性 |
| 2026-05-23 | Phase 1 首个因子选择 HV | 最基础的波动率指标，实现简单，验证数据管道 |
| 2026-05-23 | 数据源使用 tushare | A 股数据覆盖全面，需 token 认证 |
| 2026-05-23 | 首个策略用简单均值回归 | 价格偏离 20MA ±2σ 入场，回归出场。先验证管道，再迭代策略 |
| 2026-05-23 | 涨跌停判定用浮点容差 1e-8 | `(11-10)/10` 浮点结果为 0.09999... 非精确 0.1，需容差 |
| 2026-05-23 | rqalpha adapter 用 mock 测试 | rqalpha 需要 bundle 数据才能跑回测，先用 mock 验证逻辑正确 |
| 2026-05-23 | portfolio 首个策略用 equal weight | 最简单的分配方式，先验证管道再迭代 |
| 2026-05-23 | risk 新增 position_limit 而非扩展 tradability | 职责不同：tradability 管可交易性，position_limit 管仓位集中度 |
| 2026-05-23 | 回测引擎独立于 rqalpha | rqalpha 依赖重、需 bundle 数据，轻量引擎用于快速验证策略逻辑 |
| 2026-05-23 | visualization 用 matplotlib 不用 plotly | 静态图够用，plotly 交互功能当前阶段不需要 |
