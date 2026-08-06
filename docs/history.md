# yoyo-quant 开发历史

> 本文档记录各 Phase 的详细任务、测试数量和关键发现。当前状态见 `project-plan.md`。

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

## Phase 3: 策略开发 ✅ 完成

### 目标
具体策略实现和回测验证。

### 首次真实回测结果（2026-05-23）

**配置**：000001/600519/000858，2025-05-06 ~ 2026-05-22，均值回归（20MA ±2σ），等权分配，100万初始资金

**指标**：
| 指标 | 值 |
|------|-----|
| 总收益 | -0.45% |
| 年化收益 | -0.44% |
| Sharpe | -1.28 |
| 最大回撤 | 1.93% |
| 胜率 | 40.91% |
| 交易次数 | 44 笔 |

**发现**：
- 管道完整跑通，从 fetch 到 chart 无报错
- 策略信号稀疏（41 买 / 28 卖 / 696 持有），均值回归在趋势性市场触发少
- 回撤低但资金利用率也低，大量现金闲置
- 最大单笔亏损来自五粮液（-19,590），最大单笔盈利来自茅台（+7,256）

**待改进**：
- 参数敏感性分析（窗口/std 倍数）
- 增加股票池覆盖面
- 考虑加入趋势过滤或自适应参数

---

## Phase 4: 规则引擎 + 风控 + 量价因子 + 策略框架 ✅ 完成

### 目标
建立可扩展的规则引擎架构，补齐止损风控和量价因子，搭建策略组合框架。

### Task 1: 规则引擎基础设施（TDD）✅
- [x] `src/risk/rules.py` — Rule ABC 基类 + RuleContext dataclass
- [x] `src/risk/rule_engine.py` — RuleEngine（按 priority 排序执行）
- [x] 优先级分区：信号生成(0-99)、风控过滤(100-199)、交易约束(200-299)
- [x] 测试通过（15 tests）

### Task 2: 迁移现有规则到新接口（TDD）✅
- [x] `PositionLimitRule(Rule)` 包装 `apply_position_limit`（priority=150）
- [x] `TradabilityRule(Rule)` 包装 `filter_tradable`（priority=200）
- [x] `T1Rule(Rule)` 包装 `enforce_t1`（priority=210）
- [x] 原有函数保留不删除，向后兼容
- [x] 测试通过（9 new tests）

### Task 3: 止损规则（TDD）✅
- [x] `src/risk/stop_loss.py` — `FixedStopLossRule`（固定百分比止损）+ `ATRStopLossRule`（ATR 动态止损）
- [x] ATR 计算作为模块内部函数 `_calc_atr`
- [x] 止损触发时记录到 `ctx.metadata["stopped_out"]`
- [x] 测试通过（12 tests）

### Task 4: 量价因子（TDD）✅
- [x] `src/factors/volume_price.py` — 4 个因子函数
- [x] `calc_rsi(df, window=14)` — RSI，值域 [0,100]，处理边界情况
- [x] `calc_obv(df)` — OBV，首个值为 0
- [x] `calc_volume_ratio(df, window=20)` — 成交量比率
- [x] `calc_atr(df, window=14)` — ATR（从 stop_loss 提取为独立因子）
- [x] 所有因子返回 pd.Series，遵循参数无关命名约定
- [x] 测试通过（24 tests）

### Task 5: 策略框架（TDD）✅
- [x] `src/strategies/base.py` — Strategy ABC 基类
- [x] `src/strategies/combiner.py` — `WeightedVoteCombiner`（加权投票）+ `FilterCombiner`（层级过滤）
- [x] `src/strategies/registry.py` — `register_strategy` / `get_strategy` / `list_strategies`
- [x] `MeanReversionStrategy` 继承 Strategy 并注册
- [x] 原有 `mean_reversion_signal` 函数保留不删除
- [x] 测试通过（22 tests）

---

## Phase 5: 量价策略 + 目录重构 + 配置系统 ✅ 完成

### 目标
补充量价策略（RSI 反转、动量突破），重构 strategies 目录结构，建立 YAML 配置系统。

### Task 1: 目录重构 ✅
- [x] 创建 `src/strategies/builtin/` 目录
- [x] `mean_reversion.py` 移入 `builtin/`
- [x] `builtin/__init__.py` 自动导入触发注册
- [x] 更新所有 import 路径（test_mean_reversion, adapter, pipeline test）
- [x] 删除旧 `src/strategies/mean_reversion.py`

### Task 2: 量价策略（TDD）✅
- [x] `src/strategies/builtin/rsi_reversal.py` — RSI 均值回归
  - 支持 factors 预计算 RSI 或自行计算
  - 参数：window, oversold, overbought
  - 测试通过（10 tests）
- [x] `src/strategies/builtin/momentum_breakout.py` — 动量突破
  - 成交量比率 + OBV 趋势方向
  - 参数：vol_window, vol_threshold, obv_window
  - 测试通过（9 tests）

### Task 3: 配置系统（TDD）✅
- [x] `src/risk/rule_registry.py` — 风险规则注册表（名称→类映射）
- [x] `src/config/loader.py` — `load_config` + `build_strategies` + `build_risk_engine`
- [x] `configs/default.yaml` — 默认配置示例
- [x] `pyproject.toml` 添加 pyyaml 依赖
- [x] 测试通过（12 tests）

---

## Phase 6: 策略研发 + 参数分析 + 股票池 ✅ 完成

### 目标
扩大股票池，建立参数敏感性分析框架，研发并验证多个策略。

### Task 1: 股票池配置系统 ✅
- [x] `src/data/universe.py` — resolve_universe + apply_data_filters
- [x] configs/default.yaml 增加 `universe` section（30 只龙头股）
- [x] 支持手动代码列表、ST 排除、均量/均额过滤
- [x] notebook 改为从配置读取股票池
- [x] 测试通过（14 tests）

### Task 2: 参数敏感性分析框架 ✅
- [x] `src/analysis/param_sweep.py` — build_grid + run_sweep + best_result
- [x] `src/analysis/plot.py` — plot_sweep_heatmap + plot_sweep_metrics
- [x] notebooks/param_sweep.ipynb — 完整分析流程
- [x] 热力图修复：文字重叠（科学计数法）、颜色标尺（百分位 clipping）、文字颜色（背景亮度检测）
- [x] 测试通过（18 tests）

### Task 3: 策略研发与验证 ✅
对 4 个策略做参数扫描（30 只龙头股，2023-2026）：

**均值回归（Bollinger Band）**：
- 最优参数：window=25, num_std=1.5
- 最优 Sharpe：-0.44，最高收益：+0.28%
- 结论：无效。A 股龙头股不适合简单均值回归

**动量突破（Volume + OBV）**：
- 最优参数：vol_window=30, vol_threshold=3.0, obv_window=20
- 最优 Sharpe：-0.20，最高收益：+4.75%，最大回撤：1.17%
- 结论：信号太稀疏（一年 56 次），资金利用率低

**动量+趋势过滤**：
- 结论：趋势过滤反而更差（MA 滞后导致入场太晚）

**多因子选股（momentum + RSI + 低波动 + 成交量）**：
- 最优参数：momentum_window=20, rebalance=5, top_n=5, hv_window=10
- 全样本：+24.9% 收益，Sharpe 0.36
- Walk-Forward 验证：5 期中只有 2 期盈利（2024H1/2024H2），2025 年以后全部亏损
- **结论：过拟合。策略在 2024 年碰巧有效，不具备跨期稳定性**

### Task 4: 数据缓存 Bug 修复 ✅
- 发现：config 的 end_date="2024-01-01" 导致新拉的数据只到 2023 年底，旧缓存到 2025-2026，中间 2024 年完全缺失
- 修复：更新 end_date 为 2026-05-23，清除旧缓存重新拉取
- 教训：缓存数据必须验证日期连续性

### Bug 修复 ✅
- [x] 热力图文字颜色：std=0 时全白 → 改用背景亮度检测
- [x] 热力图极端值：文字重叠 → 科学计数法 + 百分位 clipping
- [x] param_sweep 裸 except → 加 logging.warning
- [x] Callable 类型签名修正

### 测试统计
- 新增测试：14 (universe) + 18 (analysis) + 9 (momentum_trend) + 10 (multifactor) = 51 tests
- 总测试数：272 tests

---

## Phase 7: GTJA 191 Alpha Factors + 策略验证 ✅ 完成

### 目标
实现 GTJA 191 高优先级因子，建立算子库+因子+策略的可扩展架构，逐类别测试策略效果。

### Task 1: 算子库（TDD）✅
- [x] `src/factors/operators.py` — 7 个 GTJA 基础算子
- [x] delay, delta, rolling_mean, rolling_std, rolling_sum, sma (EMA), corr
- [x] 测试通过（22 tests）
- [x] 后续扩展（Phase 9）：rank, ts_max, ts_min, rolling_cov → 11 个算子（39 tests）

### Task 2: GTJA 动量因子 + 策略 ✅
- [x] `src/factors/momentum.py` — 5 个动量因子（#14, #18, #20, #88, #106）
- [x] `src/factors/registry.py` — 因子注册表（主名 + GTJA 别名 + tag 过滤）
- [x] `src/strategies/builtin/gtja_momentum.py` — GTJA 动量策略
- [x] 测试通过（26 factor + 9 registry + 12 strategy = 47 tests）

### Task 3: 均值回归因子 + 策略 ✅
- [x] `src/factors/mean_reversion.py` — 4 因子（#63 6d RSI, #79 12d RSI, #112 方向平衡, #128 MFI）
- [x] `src/strategies/builtin/gtja_mean_reversion.py` — GTJA 均值回归策略
- [x] 测试通过（14 tests）

### Task 4: 量价因子 + 策略 ✅
- [x] `src/factors/volume_price_gtja.py` — 3 因子（#11 资金流, #40 涨跌量比, #43 OBV 变体）
- [x] `src/strategies/builtin/volume_price_gtja.py` — GTJA 量价策略
- [x] 测试通过（6 tests）
- [x] 后续扩展（Phase 9）：新增 15 个量价/情绪/资金流因子 → 18 因子（36 tests）

### Task 5: 波动率因子 + 策略 ✅
- [x] `src/factors/volatility_gtja.py` — 5 因子（#78 CCI, #97/#100 量波动, #161/#175 ATR）
- [x] `src/strategies/builtin/volatility_gtja.py` — GTJA 波动率策略

### Task 6: VWAP 因子 + 策略 ✅
- [x] `src/factors/vwap.py` — 2 因子（#120 VWAP/close 比率, #124 VWAP 偏离）
- [x] `src/strategies/builtin/vwap_gtja.py` — GTJA VWAP 策略

### Task 7: 趋势因子 + 策略 ✅
- [x] `src/factors/trend.py` — 3 因子（#21/#116 MA 斜率, #89 MACD-like）
- [x] `src/strategies/builtin/trend_gtja.py` — GTJA 趋势策略

### Task 8: 策略组合测试 ✅
- [x] `src/strategies/reversed.py` — ReversedStrategy 包装器
- [x] 测试 5 种组合方式：加权投票、Filter、反向均值回归
- [x] 结论：组合不超越单策略，VWAP 单独最优

### Task 9: 管道诊断工具 ✅
- [x] `src/analysis/pipeline_diagnostics.py` — 可复用的信号质量分析
- [x] 测试通过（7 tests）

### Task 10: 反向 VWAP 参数优化 ✅
- [x] 72 个参数组合扫描（rebalance × top_n × bottom_n）
- [x] 最优：rebalance=5, bottom_n=3 → Sharpe 1.11, MaxDD 8.3%
- [x] top_n 不影响结果，rebalance 是最敏感参数

### Task 11: Walk-Forward 验证 ✅
- [x] RevVWAP 全样本 Sharpe 1.11 → WF Sharpe -0.10，确认过拟合
- [x] 11 期中 6 期盈利（54.5%），策略不稳定

### Task 12: 信号质量分析 ✅
- [x] Pipeline 各阶段信号损耗分析（filter_tradable 仅过滤 0.6% 信号）
- [x] 前向收益检验：BUY 胜率 46.5%（< 50%），信号预测能力弱
- [x] 结论：Risk/Portfolio 没问题，信号质量是根本问题

### 单策略回测结果（30 只龙头股，2023-01 ~ 2026-05，rebalance=20，top_n=5，bottom_n=3）

| 策略 | 总收益 | 年化 | Sharpe | MaxDD | 胜率 | 交易数 |
|------|--------|------|--------|-------|------|--------|
| **RevVWAP** | **+71.9%** | **17.0%** | **1.11** | **8.3%** | **57.0%** | — |
| GTJA VWAP | +23.7% | 6.8% | 0.27 | 27.2% | 54.9% | 209 |
| GTJA Momentum | +18.3% | 5.3% | 0.22 | 36.1% | 45.5% | 339 |
| GTJA Vol-Price | +14.9% | 4.4% | 0.16 | 31.0% | 47.9% | 334 |
| GTJA Volatility | +12.9% | 3.8% | 0.16 | 31.2% | 48.0% | 347 |
| GTJA Trend | -18.1% | -6.0% | -0.33 | 32.3% | 39.6% | 343 |
| GTJA Mean Rev | -37.6% | -13.5% | -0.72 | 41.7% | 44.3% | 320 |

### 关键发现
1. **RevVWAP 是当时最强单策略**（Sharpe 1.11），但全样本过拟合（WF Sharpe -0.10）
2. **组合策略不超越单策略** — 弱策略稀释强信号
3. **信号质量是根本问题** — 所有因子胜率 < 50%，Spread 微弱
4. VWAP 类别天然最优（同时捕捉价格+成交量），反向 VWAP 本质变为均值回归
5. 纯动量/趋势/均值回归在 A 股龙头股上单独效果差

### 测试统计
- 新增测试：22 (operators) + 26 (momentum) + 9 (registry) + 12 (gtja_momentum) + 14 (mean_reversion) + 6 (volume_price) + 7 (pipeline) + 4 (reversed) = ~100 tests
- 总测试数：~370 tests

---

## Phase 8: Context Layer — Regime Detection + Strategy Routing ✅ 完成

### 目标
建立市场状态检测和策略切换层，实现「特定行情→特定策略」的动态路由。

### Task 1: Regime Detection v1 ✅
- [x] `src/context/regime.py` — 3 信号 regime 检测（动量共识 + 波动率 + 方向）
- [x] 4 种 regime：trend_up, trend_down, range, volatile
- [x] `src/context/regime_switch.py` — RegimeSwitchStrategy 包装器
- [x] 测试通过（11 tests）

### Task 2: Regime Detection v2（改进）✅
- [x] 信号 1：breadth（close > SMA(20) 的股票占比）替代截面 sign(20d return).mean()
- [x] 信号 2：已实现波动率（cross-sectional std of returns）+ 自适应 percentile 阈值
- [x] EMA 平滑（span=5）减少单日噪声
- [x] 最小持续期强制（min_persistence=7）确保 regime 块有意义
- [x] 测试通过（19 tests）

### Task 3: RegimeSwitchStrategy bug 修复 ✅
- [x] 修复：子策略之前只接收当天数据（无法计算技术指标），改为传截止当天的全部历史数据
- [x] 修复后 RegimeSwitch 能正确产生交易信号

### Task 4: 股票池扩展 ✅
- [x] 从 CSI 300 中按总市值取前 100（2026-05-22 数据）
- [x] 最低 1565 亿（山西汾酒），最高 26422 亿（建设银行）
- [x] 覆盖银行、非银金融、能源、通信、消费、医药、科技半导体、新能源、制造等板块

### Task 5: Reversed VWAP 注册 + 配置化 ✅
- [x] `reversed_gtja_vwap` 注册到策略表（继承 GTJAVWAPStrategy，翻转信号）
- [x] `configs/default.yaml` 新增 `strategies.regime_switch` 配置段
- [x] `src/config/loader.py` 新增 `build_regime_switch(cfg)` 构建函数

### Walk-Forward 回测结果（20 只 CSI 300，2023-01 ~ 2026-05，train=252d，test=63d）

| 期间 | Dominant Regime | Baseline | RegimeSw | Diff |
|------|----------------|----------|----------|------|
| 2024-01 ~ 2024-04 | range | -2.52% | -2.52% | 0.00% |
| 2024-04 ~ 2024-07 | range | +6.96% | +6.96% | 0.00% |
| 2024-07 ~ 2024-10 | range | +40.90% | +17.32% | -23.57% |
| 2024-11 ~ 2025-02 | range | +9.28% | +9.28% | 0.00% |
| 2025-02 ~ 2025-05 | range | -0.35% | -6.59% | -6.24% |
| 2025-05 ~ 2025-08 | range | -17.67% | +6.55% | **+24.22%** |
| 2025-08 ~ 2025-11 | range | -0.77% | -0.77% | 0.00% |
| 2025-11 ~ 2026-02 | range | -2.95% | -2.95% | 0.00% |

| 指标 | Baseline | RegimeSwitch |
|------|----------|-------------|
| 平均收益 | +4.11% | +3.41% |
| 累计收益 | +26.85% | +28.13% |
| 赢的期数 | 7/8 | 1/8 |

### 关键发现
1. **RegimeSwitch 的价值在极端行情避险**：2025-05~08 期间 baseline 亏 -17.67%，RegimeSwitch 赚 +6.55%（+24.22% 优势）
2. **大部分时期 diff=0**：dominant regime 检测结果全是 "range"，RegimeSwitch 也选 reversed_gtja_vwap，和 baseline 一样
3. **代价是错过暴涨期**：2024-07~10 baseline 涨 +40.90%，RegimeSwitch 只涨 +17.32%
4. **reversed_gtja_vwap 太强**（cum +26.85%），RegimeSwitch 很难持续跑赢
5. **Regime 检测精度不够** — 简单 breadth + 波动率无法准确捕捉市场状态切换

### 测试统计
- 新增测试：11 (regime v1) + 8 (regime v2) + 1 (bug fix) + 1 (default params) = 21 tests
- 总测试数：447 tests

---

## Phase 9: Scale-Up — 因子扩展 + 行业矩阵 + 股票选择器 ✅ 完成

### 目标
扩展因子库（量价/情绪/资金流），建立策略×行业矩阵回测框架，实现动态股票选择器。

### Task 1: 算子库扩展 ✅
- [x] `src/factors/operators.py` 新增 4 个算子：rank, ts_max, ts_min, rolling_cov
- [x] 总算子数：7 → 11
- [x] 测试更新：22 → 39 tests

### Task 2: 量价/情绪/资金流因子扩展 ✅
- [x] `src/factors/volume_price_gtja.py` 新增 15 个因子
- [x] 新增因子：#1 量变排名相关, #12 VWAP 偏离, #29 6d 收益×量, #32 高价量排名相关, #47 Williams %R 平滑, #54 K线实体波动, #70 dollar vol 波动, #80 量变化率, #90 VWAP-量排名相关, #99 收盘-量排名协方差, #102 量 RSI, #118 上下影线比, #139 开盘-量相关, #145 量 MACD, #178 日收益×量
- [x] 总量价因子数：3 → 18
- [x] 测试更新：6 → 36 tests
- [x] 全量因子数：46（含 GTJA 别名）

### Task 3: 10 年因子筛选 ✅
- [x] 30 只龙头股，2016-2026，单因子策略跑分
- [x] **TOP 发现**：
  - #118 shadow_ratio_20d（上下影线比）：Sharpe 0.56，Δ vs baseline +0.16
  - #178 return_1d_times_vol（日收益×量）：Sharpe 0.55，Δ vs baseline +0.15
  - #145 vol_macd_9_26_12：Sharpe 0.45
- [x] 大部分排名相关因子（#1, #90, #99）低于 baseline — 纯统计相关性在 A 股无效
- [x] A 股有效的是资金流类因子：谁在日内战斗中胜出（#118），以及价格波动是否有量能背书（#178）

### Task 4: 因子组合测试 ✅
- [x] BASELINE (3f: #11, #40, #43)：Sharpe 0.41, MaxDD 42.6%
- [x] **BASELINE + TOP2 (5f)**：Sharpe 0.52, MaxDD 32.3%（**最优**）
- [x] TOP2 only (2f)：Sharpe 0.49, MaxDD 36.9%
- [x] ALL 18f：Sharpe 0.45, MaxDD 29.2%
- [x] 结论：5 因子最优，加入差因子会稀释信号；#118 和 #178 提供了差异化的极端行情保护

### Task 5: 策略 × 行业矩阵回测 ✅
- [x] `src/analysis/pool_matrix.py` — run_matrix + pivot_matrix + best_per_pool
- [x] 100 只 CSI 300 按 11 个行业分组，5 策略 × 11 行业交叉回测
- [x] 3 年（2023-2026）vs 10 年（2016-2026）双窗口验证
- [x] 测试通过（12 tests）

**10 年窗口 — 各行业最优策略**：

| 行业 | 最优策略 | 年化 | Sharpe | MaxDD |
|------|---------|------|--------|-------|
| 科技半导体 | gtja_momentum | 15.7% | 0.61 | 30.6% |
| 能源资源 | reversed_gtja_vwap | 13.3% | 0.47 | 45.9% |
| 通信设备 | gtja_volatility | 14.5% | 0.46 | 62.0% |
| 电子制造 | gtja_volatility | 14.9% | 0.50 | 47.6% |
| 消费 | gtja_vwap | 13.9% | 0.49 | 38.5% |
| 装备制造 | gtja_momentum | 10.3% | 0.40 | 31.6% |
| 新能源 | gtja_vwap | 12.7% | 0.42 | 59.8% |
| 非银金融 | gtja_momentum | 6.1% | 0.24 | 47.1% |
| 银行 | gtja_volume_price | 5.6% | 0.22 | 29.9% |
| 电力公用 | gtja_vwap | 3.9% | 0.20 | 48.3% |
| 医药 | gtja_volume_price | 2.7% | 0.08 | 44.4% |

**关键发现**：
- 3 年 Sharpe 被科技牛市虚高 50-70%，10 年 Sharpe 天花板 ≈ 0.6
- gtja_momentum 是唯一跨周期稳定的策略（3 年和 10 年均排第一）
- reversed_gtja_vwap 从 3 年 #3 跌到 10 年 #5 — 其优势局限于 2023-2026
- 仅 3/11 行业在 3 年和 10 年保持了相同的最优策略
- 真实年化天花板在 A 股大市值股约 12-15%

### Task 6: 市场状态策略（MA Crossover）✅
- [x] `src/strategies/builtin/market_regime.py` — 基于指数均线交叉的仓位暴露计算
- [x] 4 种状态（bullish/neutral/cautious/bearish）映射到 [0.2, 1.0] 暴露分数
- [x] 非 Strategy 子类，产出 portfolio-level 暴露分数而非 per-stock 信号
- [x] 测试通过（15 tests）

### Task 7: 股票选择器 ✅
- [x] `src/context/stock_selector.py` — 基于因子质量的动态股票池筛选
- [x] `factor_coverage` — 因子值覆盖率 [0, 1]
- [x] `rank_stability` — 排名自相关（rank autocorrelation）[-1, 1]
- [x] `factor_dispersion` — 截面变异系数（CV ≥ 0）
- [x] `evaluate_factors` — 季度级因子审计，标记 active/inactive
- [x] `select_tradable` — 日频动态选股，按因子通过数排名
- [x] `configs/default.yaml` 新增 `stock_selector` 配置段
- [x] 测试通过（40 tests）

### 测试统计（全量）
| 模块 | 测试数 |
|------|--------|
| analysis/ | 37 |
| backtest/ | 37 |
| config/ | 12 |
| context/ | 59 |
| data/ | 39 |
| factors/ | 146 |
| portfolio/ | 16 |
| risk/ | 52 |
| strategies/ | 104 |
| visualization/ | 9 |
| **合计** | **551** |

### 关键发现总结
1. **A 股有效信号不是统计相关性，是资金流** — #118 上下影线比（日内多空战斗）和 #178 日收益×量（价格量能背书）单独跑赢 3 因子基线
2. **5 因子组合是 sweet spot** — 太少缺分散，太多稀释信号
3. **gtja_momentum 是唯一跨周期稳定的策略** — 3 年 10 年均排第一
4. **RegimeSwitch 价值在避险而非择时** — 极端行情保护 +24%，但常态下与 baseline 无差异
5. **行业差异在 10 年窗口缩小** — Sharpe 区间从 (-1.0, 1.5) 收窄到 (0.05, 0.61)
6. **股票选择器建成** — 从「固定 30/100 只」到「日频动态按因子质量筛选」，context 层第一块拼图就位

---

## 决策记录

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
| 2026-05-23 | 首次真实回测验证管道可用 | 3 只股票 1 年数据，均值回归负收益但管道无 bug |
| 2026-05-23 | 规则引擎用 ABC 而非 Protocol | ABC 更适合共同基类场景，支持 IDE 补全和类型检查 |
| 2026-05-23 | 规则引擎优先级分区而非全局排序 | 0-99/100-199/200-299 三个区域，新规则选区域即可 |
| 2026-05-23 | 止损规则放在 priority=120-121 | 风控过滤区域，在策略信号之后、交易约束之前执行 |
| 2026-05-23 | 策略和风控都用可组合架构 | 策略有组合器（加权/过滤），风控有规则引擎（链式执行） |
| 2026-05-23 | 量价因子优先于 IV/PCR | IV/PCR 需期权数据，量价因子用现有 OHLCV 即可计算 |
| 2026-05-23 | 股票池配置放在 YAML 而非代码 | 方便非程序员调整，也便于参数扫描时切换 |
| 2026-05-23 | 参数扫描的信号生成器用函数而非类 | run_sweep 需要 callable(d, **params) 接口 |
| 2026-05-23 | 热力图用 imshow 而非 seaborn | 减少依赖，手动控制更灵活 |
| 2026-05-23 | 多因子策略全样本好但 walk-forward 失败 | 典型过拟合，教训：必须做 OOS 验证 |
| 2026-05-23 | 缓存数据必须验证日期连续性 | 不同批次拉取的数据可能有日期断层 |
| 2026-05-24 | GTJA 因子采用算子+因子两层架构 | operators.py 提供可复用算子，factor 文件用算子组合，便于扩展新因子 |
| 2026-05-24 | 因子命名用描述名+GTJA编号别名 | 如 calc_momentum_5d_change (主名) + gtja_14 (别名)，兼顾可读性和论文追溯 |
| 2026-05-24 | 不重构现有因子用 operators | 现有因子模式(EWM/cumsum)与 GTJA 算子(groupby shift/rolling)不完全重合，等因子量大再统一 |
| 2026-05-24 | VWAP 是最有效的单因子类别 | 最低 MaxDD + 最高胜率，可能因为 VWAP 同时捕捉价格和成交量信息 |
| 2026-05-24 | 反向 VWAP 效果惊人 | Sharpe 0.27→0.92，MaxDD 27%→9%，本质上是均值回归策略 |
| 2026-05-24 | RevVWAP 全样本过拟合 | WF 验证 Sharpe 从 1.11 降到 -0.10，仅 54.5% 盈利期 |
| 2026-05-24 | 创建 context 层架构 | regime 检测 + 策略切换，后续扩展股票/因子/参数路由 |
| 2026-05-24 | 不追求普适性，追求特定行情有效 | 核心理念：特定行情+特定股票+特定参数+特定策略因子=长期有效 |
| 2026-05-24 | 简单 regime switch 未带来增量 | RevVWAP 8/11 盈利，RegimeSwitch 7/11；range 策略(FwdVWAP)太弱拖后腿 |
| 2026-05-24 | 股票池用 CSI 300 top 100 by market cap | 大市值股流动性好，避免小盘股噪声 |
| 2026-05-24 | regime 用 breadth 而非 sign(20d return).mean() | 二值信号的 median 只有 -1/0/1，连续 breadth 更有区分度 |
| 2026-05-24 | EMA + min_persistence 而非 majority vote | majority vote 在大窗口下反而增加切换 |
| 2026-05-25 | 扩展 15 个量价/情绪/资金流因子 | A 股是情绪/政策市，资金流因子比纯统计相关因子更有效 |
| 2026-05-25 | 默认权重用 5 因子（原 3 + #118 + #178） | 10 年跑分验证，5f 最优；差因子稀释信号 |
| 2026-05-25 | 3 年回测不可信，必须 ≥10 年验证 | 2023-2026 科技牛市虚高所有 Sharpe 50-70% |
| 2026-05-25 | 行业矩阵 + universe group 支持 | 为 context 层因子选择（按行业路由）做准备 |
| 2026-05-25 | 股票选择器放在 context 层而非 data 层 | 选择逻辑依赖因子质量评估，属于 context 路由而非纯数据过滤 |
| 2026-05-26 | context 层路线图：股票选择→因子选择→参数路由 | 逐步建立「特定行情+特定股票+特定参数+特定策略因子」的完整闭环 |

---

## Phase 10: 股票池探索 + 风控实验 ✅ 完成

### 目标
验证扩大股票池（CSI 500 / 全市场）是否提升 alpha，测试小止盈大止损效果。

### Task 1: CSI 500 中盘股扩展 ✅
- [x] `fetch_index_constituents()` — tushare `index_weight` API + parquet 缓存
- [x] `fetch_daily_batch()` — 批量获取 + 限速（0.5s/只）+ 进度日志
- [x] `resolve_universe()` 支持 `source: index`
- [x] `configs/csi500.yaml`
- [x] 对比 notebook: `notebooks/csi300_vs_csi500.ipynb`
- [x] 测试通过（18 fetcher + 24 universe + 4 pipeline tests）

**回测结果（2023-01 ~ 2026-05，5 策略）：**

| Strategy | CSI300 Sharpe | CSI500 Sharpe | Delta |
|----------|---------------|---------------|-------|
| reversed_gtja_vwap | 0.606 | 0.106 | -0.500 |
| gtja_momentum | 0.485 | 0.246 | -0.239 |
| gtja_volatility | 0.427 | 0.047 | -0.380 |
| gtja_volume_price | 0.352 | 0.369 | +0.017 |
| gtja_vwap | 0.336 | 0.382 | +0.046 |
| **平均** | **0.441** | **0.230** | **-0.211** |

**结论**：CSI 300 全面碾压 CSI 500。中盘股噪声大、趋势持续性差、流动性低（CSI 500 均量仅为 CSI 300 的 48%）。

### Task 2: MultiCategoryStrategy ✅
- [x] `src/strategies/builtin/multi_category.py` — 6 类别加权投票组合
- [x] 注册到策略表，测试通过（7 tests）

**回测结果：**

| Strategy | Sharpe | Return | MaxDD |
|----------|--------|--------|-------|
| reversed_gtja_vwap | 0.606 | 245.6% | 46.4% |
| multi_category (4cat equal) | 0.487 | 164.6% | 35.6% |

**结论**：多类别组合稀释 alpha（弱策略拖累强策略），但降低 MaxDD。

### Task 3: 小止盈大止损实验 ✅
- [x] `FixedTakeProfitRule` — 固定百分比止盈（priority=122）
- [x] `BacktestEngine` 新增 `stop_loss` / `take_profit` 参数
- [x] 注册到规则引擎，测试通过（7 tests）
- [x] `_ensure_avg_cost()` — 自动推算 entry price

**回测结果（reversed_gtja_vwap，CSI 300）：**

| Config | Sharpe | Return | MaxDD | Win% |
|--------|--------|--------|-------|------|
| No SL/TP | 0.606 | 245.6% | 46.4% | 56.2% |
| SL=-15% TP=+5% | 0.577 | 234.4% | 48.9% | 33.2% |
| SL=-15% TP=+10% | 0.585 | 238.6% | 48.8% | 46.9% |
| SL=-15% TP=+15% | 0.586 | 241.7% | 48.9% | 58.1% |

**结论**：SL/TP 对均值回归策略有害 — 止损在最低点割肉，止盈截断利润。SL/TP 适合趋势策略，不适合当前主力策略。

### Task 4: 全市场基本筛选 ✅
- [x] `fetch_all_stocks()` — tushare `stock_basic`，排除 ST + 北交所
- [x] `fetch_fundamentals()` — tushare `daily_basic`，pe/pb/total_mv
- [x] `apply_fundamental_filters()` — min_market_cap/min_pe/max_pe
- [x] `resolve_universe()` 支持 `source: "all"`
- [x] `configs/full_market.yaml`

**回测结果（reversed_gtja_vwap，2023-01 ~ 2026-05）：**

| Universe | Stocks | Sharpe | Return | MaxDD |
|----------|--------|--------|--------|-------|
| CSI 300 | 100 | 0.606 | 245.6% | 46.4% |
| Full Market | 2375 | 0.274 | 67.2% | 13.0% |

**结论**：Alpha 集中在大盘股。全市场稀释 alpha 但大幅降低 MaxDD。需要用 stock_selector 从全市场筛 top 50-100 只因子质量最高的股票。

### 测试统计
- 新增测试：18 (fetcher) + 14 (universe) + 7 (multi_category) + 7 (take_profit) + 4 (pipeline) = 50 tests
- 总测试数：633 tests

### 关键发现总结
1. **CSI 500 不提供 alpha 增量** — 中盘股噪声大，所有策略在 CSI 500 上表现更差
2. **多类别组合稀释 alpha** — 弱策略拖累强策略，但降低 MaxDD
3. **SL/TP 对均值回归有害** — 止损割肉、止盈截断利润，但可用于趋势策略
4. **Alpha 集中在大盘股** — 全市场 Sharpe 0.274 vs CSI 300 的 0.606
5. **下一步：stock_selector** — 从全市场筛 top 50-100 只因子质量最高的股票，平衡 alpha 集中度和选股空间

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-27 | CSI 500 扩展无效 | 所有策略 Sharpe 下降，中盘股噪声大、流动性低 |
| 2026-05-27 | MultiCategory 用加权投票而非独立组合 | 复用现有 WeightedVoteCombiner，改动最小 |
| 2026-05-27 | SL/TP 放在 BacktestEngine 而非 RiskRule | RiskRule 操作 target positions（无 entry price），Engine 操作 actual holdings |
| 2026-05-27 | 全市场 + stock_selector 是正确方向 | 全市场提供选股空间，stock_selector 保证因子质量 |

---

## Phase 11: Risk 层重构 + 交易费率模型 ✅ 完成

### 目标
消除 Risk 层与 BacktestEngine 之间的架构冲突（止损逻辑去同步），建立真实的 A 股交易摩擦模型。

### Task 1: 止损逻辑从 Risk 层迁移到 BacktestEngine ✅

**架构冲突**：`src/risk/stop_loss.py` 通过 `_ensure_avg_cost` 逐日循环盲推持仓成本，与 BacktestEngine 真实账户状态去同步。Risk 层止损规则"已配置但从未接入"——`walk_forward_backtest` 从不调用 `RuleEngine.run()`。

**改动**：
- [x] 增强 BacktestEngine：新增 `atr_stop_loss` 参数和 `market_data` 参数
- [x] ATR 预计算：`calc_atr` 全局计算 + `(date, code)` 键对齐（修复了排序不一致 bug）
- [x] `stopped_today` 黑名单：日循环第一行初始化，防止止损当天重新买入
- [x] `entry_prices.pop(code, None)` 同步清理，防止残留陈旧 entry_price
- [x] if-if-if 级联 + `not triggered` 守卫：ATR→固定止损→止盈，任一触发后跳过
- [x] 删除 `src/risk/stop_loss.py`（218 行）和 `tests/risk/test_stop_loss.py`（395 行）
- [x] 更新 `rule_registry.py` 和 `risk/__init__.py`，移除 3 个止损规则注册
- [x] 新增 `build_backtest_config()` 到 config/loader.py
- [x] 更新 `walk_forward_backtest` 透传止损参数和 market_data
- [x] 6 个 YAML 配置文件：止损从 `risk.rules` 移到 `backtest` 配置段
- [x] 更新 `docs/data-schemas.md`：移除 `avg_cost`，更新 trade action 枚举
- [x] 新增 10 个 ATR 止损测试（含 date-interleaved 数据对齐测试）
- 测试通过（24 → 25 tests）

### Task 2: 交易费率与滑点模型 ✅

**问题**：BacktestEngine 是理想状态撮合（零摩擦），回测夏普率含 30%+ 水分。

**改动**：
- [x] `TradingCost` dataclass：佣金（万1，最低5元）+ 印花税（万5，卖出单边）+ 过户费（十万1）+ 滑点 tick
- [x] `_calc_cost()`：零金额防御（amount ≤ 0 返回 0.0）
- [x] `_apply_slippage()`：含涨跌停价格剪裁（limit_up/limit_down）
- [x] 买入逻辑：精确逆向推算（分段函数取极小值）+ 浮点容差 0.01 元
- [x] 成本摊薄法：`entry_prices = (amount + buy_fees) / shares`，止损锚定真实盈亏平衡线
- [x] 卖出逻辑（3 处统一）：滑点 + 佣金 + 印花税 + 过户费
- [x] `day_limits` 字典：日循环顶部构建，O(1) 查询
- [x] 新增 metrics：`total_cost`（总摩擦成本）、`cost_ratio`（换手损耗率）
- [x] Trade record 新增 `cost` 列
- [x] `__post_init__` 验证：负值抛 ValueError
- [x] `walk_forward_backtest` 结果传播 total_cost/cost_ratio
- [x] `build_backtest_config` 支持 trading_cost 段
- [x] `configs/default.yaml` 新增 backtest.trading_cost 配置
- [x] 更新 `docs/data-schemas.md`：cost 列、total_cost/cost_ratio 指标
- [x] 新增 14 个摩擦测试（含 PnL 生命周期对账、涨跌停剪裁、边界资金）
- 测试通过（25 → 39 tests）

### Code Review 修复 ✅

| Issue | 严重性 | 修复 |
|-------|--------|------|
| ATR map 对齐 bug（calc_atr 内部排序不一致） | Critical | 对 market_data 按 ["code","date"] 排序后再计算 |
| 弱断言（test_stopped_today/test_entry_prices） | Important | 改为 3 天场景 + PnL 验证 |
| win_rate 排除止损交易 | Important | 扩展 exit_actions 列表 |
| TradingCost 无输入验证 | Important | 新增 __post_init__ |
| walk_forward 丢失成本指标 | Important | 结果新增 total_cost/cost_ratio |
| 缺少边界资金测试 | Important | 新增 test_insufficient_funds_after_fees |
| 缺少止损路径对账 | Important | 新增 test_pnl_lifecycle_stop_loss |

### 测试统计
- 新增测试：10 (ATR stop-loss) + 14 (trading cost) = 24 tests
- 删除测试：17 (risk stop_loss)
- 净增：+7 tests
- 总测试数：677 tests

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | 止损逻辑从 Risk 层移到 BacktestEngine | Risk 层盲推 avg_cost 与 Engine 真实账户去同步；规则从未被接入 |
| 2026-05-28 | 成本摊薄法而非分离记录 | entry_prices 含买入费用，止损锚定真实盈亏平衡线 |
| 2026-05-28 | 逆向推算分段函数而非简单预扣 | 大额交易时比例佣金 > 5 元底线，需取两种情况极小值 |
| 2026-05-28 | 浮点容差 0.01 元而非 min 截断 | 保证数学守恒：cash_delta == sum(pnl) |
| 2026-05-28 | 涨跌停剪裁在 _apply_slippage 内部 | 买入和卖出统一处理，防止滑点超越法定边界 |
| 2026-05-28 | TradingCost 用 dataclass 而非 dict | 类型安全 + 默认值 + __post_init__ 验证 |

---

## Phase 12 补充：全周期连续回测 + Dead-Zone + Fast Recovery ✅ 完成

### 全周期连续回测（路径 A）

**问题**：walk-forward 每 period 重置 initial_capital，CB 的 HWM 被抹平，导致跨 period 状态断裂。

**方案**：直接用 BacktestEngine.run() 跑完整 10 年（2016-05 ~ 2026-05），单次连续运行。

**结果**：

| 配置 | Return | Sharpe | MaxDD | CB Trades |
|------|--------|--------|-------|-----------|
| **Baseline** | **211.9%** | **0.611** | -33.4% | — |
| CB-10% | 46.1% | 0.383 | -14.4% | 2594 |
| CB-15% | 60.7% | 0.397 | -17.5% | 2814 |
| CB-25% | 76.8% | 0.400 | -24.4% | 1849 |
| CB-35% | 139.6% | 0.535 | -27.8% | 1772 |
| CB-40% | 157.6% | 0.545 | -29.6% | 1736 |
| CB-50% | 185.5% | 0.577 | -31.6% | 1702 |

**结论**：CB 在连续 HWM 下确实有效降低 MaxDD（-33.4% → -14.4%），但 Sharpe 全面下降。阈值越低，避险越强但踏空越严重。

### Dead-Zone + Fast Recovery（方案 1 + 2）

**Dead-Zone**：只有当 exposure 变化超过步长（默认 0.05）时才调整持仓。CB Trades 从 2814 降至 1811（-36%）。

**Fast Recovery**：当策略净值 3 日反弹超过阈值（默认 5%），强制 exposure 重置为 1.0，绕过慢速 hysteresis。在 2025-08/09 月份帮助追涨 +3.4%/+13.7%。

**组合效果**：

| 配置 | Return | Sharpe | MaxDD | vs Baseline |
|------|--------|--------|-------|-------------|
| Baseline | 211.9% | 0.611 | -33.4% | — |
| CB-35% DZ5 FR5 | 139.6% | 0.535 | -27.8% | Sharpe -0.076, MaxDD +5.6pp |
| CB-50% DZ5 FR5 | 185.5% | 0.577 | -31.6% | Sharpe -0.034, MaxDD +1.8pp |

### 最终结论

**DrawdownCircuitBreaker 作为 Sharpe 提升工具已到极限**：
- 在 10 年窗口内，-50% drawdown 也不算尾部事件，CB 无法区分"正常回撤"和"系统性危机"
- CB 的价值在于 MaxDD 压缩（风控目标），不在于 Sharpe 提升（收益目标）
- 最优安全底线：threshold=-0.35，作为熔断保底，不作为常态策略

**已修复的 Bug**：`_apply_slippage` 将 boolean `limit_up/limit_down` 当作价格处理，导致 `min(price, False)=0`。修复为类型检查，忽略 boolean 值。

### 测试统计
- 总测试数：685 tests

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | CB 阈值锁定 -0.35 作为安全底线 | -35% 是 10 年窗口内唯一可区分的极端尾部事件（2018-10 -33.4%） |
| 2026-05-28 | 停止 CB 逻辑复杂度堆砌 | Sharpe 天花板由因子质量决定，非风控层可突破 |
| 2026-05-28 | _apply_slippage 忽略 boolean limit_up/down | market_data 的 limit_up/down 是 bool 标志，不是价格 |

---

## Phase 12: Drawdown Circuit Breaker ✅ 完成

### 目标
实现基于回撤的非对称仓位压缩断路器，降低系统性大回撤（MaxDD），同时保持牛市进攻火力。

### 设计理念
Phase 8 的教训：用宏观 regime 做策略路由失败（踏空 +24% 暴跌中避险成功，但 -24% 暴涨中踏空）。方案 A 的核心是**不做策略切换，只做仓位压缩**：
- 正常市场：满额暴露（exposure=1.0），策略完全不受干扰
- 回撤触发：渐进压缩仓位（exposure 降到 min_exposure），保留底仓避免完全踏空
- 恢复滞后（hysteresis）：触发阈值比恢复阈值更严，避免震荡触发

### Task 1: DrawdownCircuitBreaker 实现（TDD）✅

**文件**：`src/portfolio/circuit_breaker.py`

**类**：`DrawdownCircuitBreaker`
- `threshold`：触发阈值（如 -0.15 = -15% 回撤）
- `recovery_threshold`：恢复阈值（如 -0.05 = -5%），比触发阈值更浅
- `min_exposure`：最小暴露度（如 0.1 = 10%）
- `ramp_speed`：恢复曲线曲率（默认 2.0，幂函数插值）
- `compute_exposure(equity)`：从净值曲线计算每日 exposure
- `_drawdown_to_exposure(dd)`：drawdown → exposure 映射函数
- `reset()`：重置内部状态（engine 每次 run 调用）

**暴露度映射**：
```
drawdown >= recovery_threshold  →  exposure = 1.0（满额）
drawdown <= threshold           →  exposure = min_exposure（最小）
中间区域                         →  幂函数插值（渐进过渡）
```

- 测试通过（18 tests）

### Task 2: BacktestEngine 集成 ✅

**架构决策**：CB 放在 BacktestEngine 内部而非 walk_forward 层。

原因：walk-forward 每个 period 用 `initial_capital` 重新开始，如果 CB 在 walk_forward 层监控跨 period 净值，新 period 起始净值低于上一个 period 的 peak，会立刻触发伪回撤。

**Engine 改动**（`src/backtest/engine.py`）：
- [x] `__init__` 新增 `circuit_breaker` 参数
- [x] 日循环开始时：用 `_prev_equity`（昨日净值）计算 drawdown，得到 exposure
- [x] exposure < 1.0 时：按比例压缩 target shares
- [x] 卖出逻辑增强：从"不在 target 则卖"改为"持有超过 target 则卖"（支持 CB 压缩后减仓）
- [x] 日循环结束时：更新 `_prev_equity`
- [x] `run()` 开头：`circuit_breaker.reset()`（每个 period 独立）

**卖出逻辑重构**：
原逻辑：`if code not in target → sell all`
新逻辑：`if holdings[code] > target[code] → sell excess`
- target=0 且 holding>0 → action="sell"（完全清仓）
- target>0 且 holding>target → action="cb_compress"（CB 压缩减仓）

### Task 3: walk_forward 集成 ✅

**改动**（`src/backtest/walk_forward.py`）：
- [x] `walk_forward_backtest` 新增 `circuit_breaker` 参数
- [x] 透传到 `BacktestEngine(circuit_breaker=circuit_breaker)`
- [x] 移除旧的 `exposure_fn` CB 集成（CB 现在在 engine 内部）

### 回测结果

**配置**：CSI 300（100 stocks），2023-01 ~ 2026-05，walk-forward 12m/3m
**策略**：50% gtja_momentum + 50% reversed_gtja_vwap（定版配置）
**止损**：-15%

| 配置 | Cumulative | MaxDD | Sharpe | CB wins |
|------|-----------|-------|--------|---------|
| Baseline | 149.7% | 9.9% | 0.34 | — |
| CB threshold=-0.15 | 143.2% | 8.6% | 0.07 | — |
| CB threshold=-0.10 | 121.6% | 7.4% | -0.08 | 16/35 |
| CB threshold=-0.08 | 108.1% | 6.6% | -0.14 | — |

**Per-period 亮点（CB -0.10 vs Baseline）**：
- Period 34（最大回撤期）：Baseline -22.2% vs CB -9.9%（避险 +12.3%）
- Period 24：Baseline -1.2% vs CB +7.2%（反转 +8.4%）
- Period 29：Baseline -8.8% vs CB -3.8%（避险 +5.0%）
- Period 11（暴涨期）：Baseline +36.0% vs CB +21.7%（踏空 -14.3%）

### 测试统计
- 新增测试：18 (circuit_breaker) + 4 (engine CB) + 3 (walk_forward CB) = 25 tests
- 总测试数：685 tests

### 关键发现

1. **CB 有效降低 MaxDD**：threshold=-0.08 降 33%，-0.10 降 25%，-0.15 降 13%
2. **代价是收益压缩**：CB 在坏行情避险（16 periods），但也在好行情踏空（19 periods）
3. **Walk-forward 结构限制**：每个 period 从 initial_capital 重新开始，CB 只能监控单 period 内 drawdown（63 天窗口），无法捕获跨 period 持续回撤
4. **非对称设计验证**：CB 在 period 34（-22.2% → -9.9%）展示了 Phase 8 中验证过的避险能力
5. **Sharpe 未提升**：CB 压缩了收益波动但没有提升风险调整后收益，说明在当前框架下避险收益 < 踏空损失

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | CB 放 portfolio 层而非 risk 层 | 输出是 exposure Series，直接对接 allocator；不改 RuleContext |
| 2026-05-28 | CB 在 engine 内部而非 walk_forward 层 | walk-forward 跨 period 净值不连续，会触发伪回撤 |
| 2026-05-28 | 每个 period 独立 reset | walk-forward 每 period 重新开始，CB 应监控单 period 内 drawdown |
| 2026-05-28 | 卖出逻辑从"不在 target"改为"超过 target" | 支持 CB 压缩后按比例减仓，而非只能完全清仓 |

---

## Phase 13：因子层行业中性化（2026-05-28）

### 任务

在因子值进入截面排名之前，剥离行业暴露，让因子纯粹捕捉个股 alpha。与组合层行业 cap（已验证无效）不同，这是在信号生成阶段净化因子本身。

### 实现

- 新增 `src/factors/neutralize.py`：`demean_by_industry()` 矩阵向量化 + `min_peers` 动态降级防排名死锁
- 修改 6 个 GTJA 策略文件：加 `industry_map` / `min_peers` 参数，rank 前调 neutralize
- 修改 `src/config/loader.py`：`build_industry_map()` + `_inject_neutralization()`，全链路透传（含 regime_switch 路径）
- 26 个新测试（18 单元 + 8 管道），总测试 730 个

### A/B 回测结果

100 股（CSI 300 top 100），10 年 walk-forward，neutralization.enabled vs disabled：

| 策略 | Sharpe (Raw) | Sharpe (Neutral) | Delta | MaxDD Delta |
|------|:-----------:|:----------------:|:-----:|:-----------:|
| reversed_gtja_vwap | 0.316 | **0.873** | **+0.557** | -1.1% |
| gtja_volume_price | 0.281 | **0.789** | **+0.508** | -1.6% |
| gtja_volatility | 0.520 | **0.887** | **+0.367** | -2.9% |
| gtja_trend | 0.022 | 0.144 | +0.122 | -0.8% |
| gtja_momentum | 0.225 | 0.150 | -0.075 | +0.2% |
| gtja_mean_reversion | 0.168 | 0.036 | -0.131 | +0.7% |

### 关键发现

1. **4/6 策略中性化后显著改善**，最佳单策略 Sharpe 从 0.520 飙升至 0.887（gtja_volatility）
2. **"真假 Alpha" 现形**：VWAP/波动率/量价因子是真正的个股 alpha；动量/均值回归本质上在赚行业轮动的 beta
3. **生产组合（50/50 momentum+vwap）必须重构**：momentum Sharpe 降至 0.150，继续持有 50% 权重将严重拖累组合
4. **Sharpe 0.6 天花板被打破**：中性化后单策略可达 0.887，具备实盘交割水准

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | 截面去均值而非回归或行业内排名 | 去均值 = OLS 回归残差（单维度等价），比回归简洁，比行业内排名温和 |
| 2026-05-28 | min_peers=3 动态降级 | 单股票行业去均值后归零，在 rank(pct=True) 中产生排名死锁 |
| 2026-05-28 | 静态行业分类（已知前视偏差） | Tushare 无 point-in-time 行业数据，先用最新快照近似 |
| 2026-05-28 | 默认 enabled=false | 需要用户主动开启，避免意外改变现有回测结果 |

---

## Phase 14：组合层相关性校准与策略池剪枝（2026-05-28）

### 任务

基于中性化后的策略截面相关性矩阵，对策略池执行刚性剪枝，锁定核心双子星组合。

### 相关性矩阵（中性化后，10 年 daily returns）

```
               momentum   rev_vwap   mean_rev  vol_price      trend volatility
    momentum      1.000      0.524      0.459      0.620      0.705      0.615
    rev_vwap      0.524      1.000      0.447      0.505      0.582      0.467
    mean_rev      0.459      0.447      1.000      0.493      0.503      0.478
   vol_price      0.620      0.505      0.493      1.000      0.564      0.544
       trend      0.705      0.582      0.503      0.564      1.000      0.597
  volatility      0.615      0.467      0.478      0.544      0.597      1.000
```

### 关键发现

1. **相关性 0.45-0.71 是纯多头框架的理论下限**：剥离行业均值后，残存的正相关来自全市场系统性风险暴露、大市值风格暴露、GTJA 算子间非线性共线性。无空头对冲时，截面多头组合相关性下限约 0.40。

2. **1 天理想 Sharpe vs 真实 Sharpe 的断裂**：trend 策略 1 天理想 Sharpe 1.088，walk-forward 后坍塌至 0.144。典型的"高频高换手陷阱"——印花税 + 过户费 + 1-tick 滑点以天为单位指数级吃掉净值。框架主要矛盾已从"缺乏 Alpha"转移到"交易摩擦控制"。

3. **最佳分散对 = A/B 测试最高 Sharpe 对**：rev_vwap × volatility（相关性 0.467），两者中性化后 Sharpe 分别为 0.873 和 0.887。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | 剔除 mean_rev（Sharpe 0.036） | 零期望资产无法贡献净值，只增加调仓摩擦 |
| 2026-05-28 | 剔除 momentum（Sharpe 0.150） | 与 rev_vwap 相关性 0.524，与 trend 共线 0.705，信号冗余 |
| 2026-05-28 | 剔除 trend（Sharpe 0.144） | 高频高换手陷阱，摩擦损耗远超 alpha |
| 2026-05-28 | 剔除 vol_price（Sharpe 0.789） | 虽然不错，但与 rev_vwap 相关性 0.505，加入后不如纯双子星 |
| 2026-05-28 | 锁定核心双子星：rev_vwap + volatility | 相关性 0.467（最低），Sharpe 分别 0.873/0.887，MPT 组合穿透 1.0 |
| 2026-05-28 | 下一步：风险平价组合器替代等权 | 基于真实波动率+协方差动态分配，而非固定权重 |

### 下一步计划

- 实现 Risk Parity 组合器（`src/portfolio/risk_parity.py`）
- 用 rev_vwap + volatility 双子星回测验证 Sharpe ≥ 1.0
- 校准 regime switch 路由：volatility 用于 volatile/trend_down 状态，rev_vwap 用于 range/trend_up 状态

---

## Phase 15：基本面盈利断层因子（2026-05-28）

### 任务

引入与价量异构的纯基本面因子作为第 3 颗星，打破 Sharpe 0.820 天花板。

### 实现

**数据层**（`src/data/earnings.py`，新建）：
- `fetch_forecast(ts_code)` / `fetch_express(ts_code)` — tushare 业绩预告/快报，逐股票拉取
- `fetch_earnings_history(codes)` — 批量获取，parquet 缓存
- `_compute_pit_surprise()` — PIT 滚动池状态机：Forecast 用类型评分，Express 用同池 rank_diff
- `_compute_acceleration()` — 显式季频匹配（Q1→去年年报，Q2→Q1，Q3→Q2，Q4→Q3）
- `build_earnings_panel()` — 日频面板 + 每日截面 Z-Score 标准化（clip [-3, 3]）

**因子层**（`src/factors/earnings.py`，新建）：
- `calc_earnings_surprise()` / `calc_earnings_acceleration()` — 透传预计算值

**策略层**（`src/strategies/builtin/earnings_surprise.py`，新建）：
- `GTJAEarningsSurpriseStrategy` — 复用 volatility_gtja 模式，rank → composite → top_n/bottom_n

**测试**：46 个新测试（27 数据 + 7 因子 + 12 策略），总测试 776 个

### A/B 回测结果

100 股（production.yaml），10 年 walk-forward（2016-06 ~ 2026-05）：

> **注意（2026-05-29 修正）**：以下 Sharpe 为各期 per-period Sharpe 的算术平均，Return 为各期
> compound，均非基于连续权益曲线的正确指标。已修复 `walk_forward.py`，新增 `compute_overall_metrics`
> 从连续日收益序列计算。旧数字保留作相对比较参考，绝对值需重跑确认。

| 配置 | Sharpe | MaxDD | Return | Trades |
|------|--------|-------|--------|--------|
| twin-star/0.52（基线） | 0.818 | 7.8% | 309.6% | 920 |
| **earn-N10/rb15** | **0.978** | **7.3%** | **369.8%** | 2217 |
| earn-N10/rb10 | 0.971 | 7.2% | 379.1% | 2330 |
| earn-N10/rb20 | 0.961 | 7.3% | 355.4% | 2087 |
| earn-heavy/t0.3 | 0.966 | 7.0% | 293.2% | 2054 |
| triple-N10/t0.2 | 0.896 | 6.4% | 200.8% | 3118 |
| triple-equal/t0.5 | 0.157 | 3.4% | 80.4% | 395 |

### 关键发现

1. **earnings-only N=10 rb=15 达到 Sharpe 0.978**，突破 Phase 14 的 0.820 天花板（+19.6%）
2. **纯基本面 > 混合组合**：earnings-only 0.978 > triple-N10 0.896。基本面 alpha 与价量 alpha 混合后被 AND-gate 稀释
3. **top_n=10 优于 top_n=5**：更分散的持仓降低特异性风险
4. **threshold 对单策略无影响**：earnings-only 时 threshold=0.0 和 0.3 结果相同

### 设计亮点

- **PIT 滚动池状态机**：Forecast/Express 分池处理，杜绝 None 排名崩溃和非对称分母
- **跨年动态回溯**：Q1(0331) → 去年年报(1231)，Q1 加速度非真空
- **日频截面 Z-Score**：消灭小样本异方差和异构分布差分问题
- **四月双重披露保护**：按 (ann_date, end_date) 排序，更新季胜出

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-28 | Forecast/Express 分池 PIT | 同池会导致 None 排名崩溃和非对称分母 |
| 2026-05-28 | 截面 rank 差替代绝对值归一化 | 天然有界 [-1,1]，抗离群值 |
| 2026-05-28 | 砍掉 pead_momentum | 本质是价格动量的马甲，走私回价量因子 |
| 2026-05-28 | 日频截面 Z-Score 标准化 | 消灭小样本异方差和 Forecast/Express 尺度断裂 |
| 2026-05-28 | Q1 跨年链接去年年报 | Q1 加速度非真空，显式 prev_end_date 匹配 |
| 2026-05-28 | 生产配置切换为 earnings-only | 纯基本面 Sharpe 0.978 > 混合 0.896 |

### 生产级参数矩阵网格搜索（2026-05-28）

**扫描轴**：top_n (10/15) × weights (0.35/0.35/0.30 vs 0.40/0.40/0.20) × threshold (0.4/0.5/0.6) × dead_zone (0.015)

| # | 配置 | Sharpe | Std | MaxDD | Return | Trades |
|---|------|--------|-----|-------|--------|--------|
| 1 | earn-only/N10/rb15 | **0.989** | 1.802 | 7.3% | 362.8% | 2152 |
| 2 | earn-only/N10/rb20 | 0.977 | **1.777** | 7.2% | 352.2% | 2073 |
| 3 | earn-only/N12/rb20 | 0.947 | 1.821 | 7.2% | 299.1% | 2308 |
| 4 | earn-only/N12/rb15 | 0.938 | 1.885 | 7.3% | 291.0% | 2425 |
| 5 | earn-only/N15/rb15 | 0.831 | 1.932 | 6.9% | 226.2% | 2790 |
| 6 | earn-only/N15/rb20 | 0.780 | 1.910 | 7.0% | 195.7% | 2597 |
| 7 | triple/w35/N15/t0.5 | 0.506 | 1.788 | 9.4% | 125.5% | 1177 |
| 8 | triple/w40/N15/t0.5 | 0.493 | 1.790 | 9.4% | 115.6% | 1189 |
| 9 | triple/w35/N10/t0.5 | 0.000 | overflow | 6.7% | 50.4% | 609 |
| 10 | triple/w40/N10/t0.5 | 0.000 | overflow | 6.8% | 45.0% | 615 |

**目标达成情况**：
- Sharpe > 1.0：**未达成**（最高 0.989，差 0.011）
- Std < 1.2：**未达成**（最低 1.777，结构性卡在 ~1.8）

**关键发现**：
1. **N=10 是最优 top_n**：N=12/15 分散过度稀释 alpha，Sharpe 从 0.989 降至 0.780
2. **rb=15 略优于 rb=20**：更快响应基本面变化，但差异极小（0.012）
3. **Triple-star 全面劣于 earnings-only**：AND-gate 在三策略下过于保守，N=10 时信号几乎被完全过滤
4. **Threshold 对 triple 无影响**：0.4/0.5/0.6 结果相同，说明瓶颈在信号交集而非门槛
5. **跨期 Std 结构性卡在 ~1.8**：这是 walk-forward 框架的固有属性（12m/3m 窗口），非因子或策略问题
6. **Sharpe 0.989 ≈ 1.0**：距离目标仅差 1.1%，可能通过微调 rebalance 或扩大股票池突破

---

## Phase 16：Walk-Forward 修正 + 市场选择 + 连续回测（2026-05-29）

### 任务

1. 修正 walk-forward metrics 聚合方式（per-period 平均 → 连续权益曲线）
2. 对比 CSI 300 / CSI 500 / CSI 1000 上 earnings_surprise 的表现
3. 引入连续回测框架，对比 walk-forward vs continuous

### 实现

**walk_forward.py 修正**：
- `walk_forward_backtest()` / `walk_forward_multi_silo()` 返回 dict（per_period + overall + equity_curve）
- 资金跨期链式传递（`starting_capital` 参数）
- `compute_overall_metrics()` 从连续权益曲线计算 Sharpe / 年化收益 / MaxDD
- Sharpe 计算中 `std > 1e-10` 防浮点噪声

**engine.py 修正**：
- `BacktestEngine.run()` 新增 `starting_capital` 参数，覆盖 `initial_capital`

**continuous.py 新建**：
- `continuous_backtest()` — 单次通过，无 train/test 切分
- `compute_continuous_metrics()` — 从连续权益曲线计算指标

**测试**：新增 9 个 continuous tests + 更新 22 个 walk-forward tests，总测试 786 个

### 三市场 earnings_surprise 对比（corrected overall metrics）

| 市场 | 配置 | Sharpe | MaxDD | Return | 数据长度 |
|------|------|--------|-------|--------|---------|
| **CSI 500** | earn/N10/rb15 | **0.930** | **14.4%** | 36.9% | 3.4y |
| CSI 300 | earn/N10/rb15 | 0.665 | 25.2% | 171% | 10y |
| CSI 1000 | earn/N15/rb15 | 0.220 | 39.4% | 56.9% | 3.4y |
| CSI 1000 | twin-star/N25 | -0.135 | 54.1% | -22.4% | 3.4y |

**关键发现**：
1. **CSI 500 是 earnings_surprise 的甜区** — 中盘股分析师覆盖少、盈利预期偏差大，信息不对称产生最强 alpha
2. **twin-star（量价因子）在 CSI 500/1000 全面失效** — 微观结构因子只在大盘流动性好的股票上有效
3. **CSI 1000 数据质量不够** — tushare 限流导致大量小盘股无 earnings 数据，信号退化严重
4. **之前"CSI 500 无效"的结论只适用于量价策略**，基本面因子在中盘股上更有效

### Walk-Forward vs Continuous 对比（CSI 500, earn/N10）

| 指标 | Walk-Forward | Continuous | 差异 |
|------|-------------|-----------|------|
| Sharpe | 0.930 | **0.333** | -64% |
| 年化收益 | 15.91% | **8.17%** | -49% |
| MaxDD | 14.36% | **32.36%** | +125% |
| 总收益 | 36.89% | 29.01% | -21% |

**连续回测年度拆解**：

| 年份 | 收益 | MaxDD |
|------|------|-------|
| 2023 | **-26.7%** | 31.8% |
| 2024 | +41.6% | 22.6% |
| 2025 | +23.8% | 7.1% |
| 2026 | +0.5% | 8.6% |

**关键发现**：
1. **walk-forward 完全掩盖了 2023 年的暴跌** — 每 3 个月重置资金，-26.7% 的回撤被截断
2. **真实投资者体验**：先亏 26%，再用两年赚回来
3. **诚实指标**：Sharpe 0.33, 年化 8.2%, MaxDD 32.4%
4. **2024-2025 表现不错**（年化 ~30%），策略在特定市场环境下有效

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-29 | 生产配置切换到 CSI 500 + earnings-only | CSI 500 earnings Sharpe 0.930 > CSI 300 的 0.665 |
| 2026-05-29 | 去掉 SL/TP | 对 earnings 策略（基本面驱动）无意义 |
| 2026-05-29 | 保留 walk-forward 但标注局限性 | 连续回测验证了策略有效性，walk-forward 用于参数选择仍合理 |

**结论**：earnings-only N=10 rb=15 是当前最优配置。Std < 1.2 需要架构层面改变（拉长 test_months、引入跨 period 状态累积、或切换到连续回测模式）。

---

## Phase 17: 多源因子扩展 ✅ 完成

### 目标
引入不同经济来源的因子（价值、质量、流动性），提高因子分散化和 IR。

### 背景
- 37 个 GTJA 因子 + 2 个 earnings 因子全部来自同一经济来源（价格-成交量行为）
- Walk-forward IR 仅 0.225，因子间相关性 0.45-0.71
- 需要不同经济来源的因子来打破 IR 天花板

### 新增因子（7 个）

| 类别 | 因子 | 说明 |
|------|------|------|
| 价值 | `calc_ep` | EP = 1/PE（线性化，PE<=0 → NaN） |
| 价值 | `calc_bp` | BP = 1/PB（同上） |
| 质量 | `calc_roe_level` | ROE 水平（高质量 = 高 ROE） |
| 质量 | `calc_roe_stability` | ROE 稳定性（8 季度 std 取负，越稳定分数越高） |
| 质量 | `calc_cashflow_quality` | 每股经营现金流（OCFPS） |
| 流动性 | `calc_amihud` | Amihud 非流动性 = mean(|return| / turnover) |
| 流动性 | `calc_turnover` | 换手率 = volume * close / total_mv |

### 新增数据源
- `src/data/fundamentals_quarterly.py` — 调用 `pro.fina_indicator()` 获取季度财务指标
  - PIT 对齐：`merge_asof` backward on `ann_date`（非 `end_date`，避免前视偏差）
  - Z-Score 标准化（同 earnings.py 模式）
  - 字段：roe, ocfps

### 跳过的因子
- **分析师修正**：`analyst_forecast` 接口在 proxy 上不可用，`report_rc` 需额外权限
- **盈利动量**：用 `forecast` API 构造的信号与现有 `earnings_surprise` 高相关，无分散化价值
- 用户决策：跳过，把精力放在质量因子上

### 新增策略
- `fundamental_diversified` — 组合非价格因子，截面排名加权打分
  - 候选池 9 个因子（ep/bp/amihud/turnover/roe_level/roe_stability/cashflow_quality/earnings_surprise/earnings_acceleration）
  - 单因子 walk-forward 评估后只保留 3 个：earnings_surprise（盈利）/ amihud（流动性）/ roe_stability（质量），每类经济来源各取一个
  - 其余候选（ep/bp/turnover/roe_level/cashflow_quality/earnings_acceleration）无分散化增益，未纳入组合
- 配置：`configs/fundamental_diversified.yaml`

### 测试
- 47 个新测试（test_value.py: 17, test_liquidity.py: 13, test_quality.py: 10, test_fundamentals_quarterly.py: 7）
- 全量 833 测试通过

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-29 | 跳过盈利动量因子 | 与 earnings_surprise 高相关，无分散化价值 |
| 2026-05-29 | ROE 拆分为 level + stability | "高质量"和"稳定质量"是不同目标，让数据决定 |
| 2026-05-29 | EP/BP 用倒数而非原始 PE/PB | EP 是线性的，PE 的倒数关系让极端值失真 |
| 2026-05-29 | 质量因子用 passthrough 模式 | 季度数据的 PIT 对齐和滚动计算在数据层完成 |

**评估脚本**：`notebooks/evaluate_new_factors.py` — 单因子 walk-forward IR + 相关性矩阵 + 组合策略评估

### 收尾补充（2026-05-30 补）
- **补测试**：`tests/strategies/test_fundamental_diversified.py` 新增 21 个策略测试（此前策略无任何测试覆盖）——契约列/signal 值域与 dtype/confidence 范围/warmup 边界/单股票与短历史/空数据/自定义权重/行业中性化/无重复行
- **修 bug**：`fundamental_diversified_signal` 对空 DataFrame（带因子列）输入时 `all_dates[-1]` 越界 IndexError，新增空输入早退分支
- **文档修正**：策略 docstring / project-plan / 本文件此前写"7 因子"，实际候选池 9 个因子、评估后仅保留 3 个（earnings_surprise/amihud/roe_stability）；`evaluate_new_factors.py` 的 "Combined (7 factors)" 实验标签修正为实际组合
- **清理**：`src/factors/__init__.py` 的 `__all__` 中 `calc_amihud` 重复项删除
- 全量 **854 tests 通过**（62 个测试文件）

---

## Phase 18: 统一管道编排（P0-02）✅ 完成

### 目标
消除 4 处手写重复的回测管道，收敛为单一编排入口，消除"改一处契约需同步 4 处"的维护隐患。

### 现状（修复前）
`signal → filter_tradable → enforce_t1 → equal_weight → position_limit → BacktestEngine` 在 4 处各手写一遍：
- `src/backtest/walk_forward.py`（主链 + `_run_silo_pipeline`）
- `src/backtest/continuous.py`
- `src/analysis/param_sweep.py` `_run_single`
- `src/analysis/pool_matrix.py` `run_matrix`

各入口能力不一致：smoother/industry_cap/止损/成本/断路器仅 walk_forward/continuous 支持；param_sweep/pool_matrix 的 prices 构造不 `drop_duplicates`。

### 变更
- 新增 `src/backtest/pipeline.py`，三个公开函数：
  - `build_positions(signals, data, capital, ...)`：filter → enforce_t1 → [rebalance 稀疏化] → equal_weight → [smoother]，返回 `(positions, prices)`。silo 管道复用（不做 cap/limit，保持原行为）。
  - `run_backtest(positions, prices, data, ...)`：positions → BacktestEngine 结果（trades/equity_curve/metrics）。multi_silo 合并后段复用。
  - `run_pipeline(signals, data, capital, ...)`：完整链 + industry_cap + position_limit，返回 `{positions, carry_positions, prices, trades, equity_curve, metrics}`。walk_forward/continuous/param_sweep/pool_matrix 复用。
- **行为对齐**（用户确认）：param_sweep/pool_matrix 对齐到完整版——prices 统一 `drop_duplicates`；引擎统一支持止损/止盈/成本/断路器/exposure/smoother/industry_cap（默认关闭，默认参数下结果不变）。
- **carry_positions 语义**：cap/limit 前的中间态（equal_weight/smoother 输出），用于 walk-forward 跨期 smoother 冷启动，保持原 `prev_positions` 行为（原代码在 industry_cap 之前 copy）。
- `build_positions` 支持 `market_data` 透传：跨期 smoother 需从全量数据（含上一期日期）查 prev-day prices，walk_forward 与 silo 均传入完整 `data`。

### 测试
- 新增 `tests/backtest/test_pipeline.py`（17 tests）：正常路径 / 涨停过滤 / exposure / rebalance 稀疏化 / 跨期冷启动（resurrected 股票经死区保留）/ 与手工链等价性 / industry cap / position limit / 空信号边界 / 缺列报错
- 全量 **897 tests 通过**（854 单元 + 26 管道 + 17 新增），ruff check + format 通过
- 修复过程中顺带修正 param_sweep.py 既有 lint 问题（UP035/E402/E501）

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | 统一入口放 `src/backtest/pipeline.py` | 管道产出回测结果，放 backtest 层最自然，analysis 反向依赖 backtest 已有先例 |
| 2026-06 | 三个公开函数而非一个 | silo 需要「信号→仓位」前半段（不含 cap/limit），必须能拆出 |
| 2026-06 | param_sweep/pool_matrix 对齐到完整管道 | 默认参数下结果不变；统一后可获得完整能力（止损/成本/断路器/exposure） |
| 2026-06 | multi_silo 合并后段保留 cap/limit 两行 API 调用 | 输入已是合并后 positions，无法走 run_pipeline（其输入为 signals）；engine 段已收敛到 run_backtest |

---

## Phase 19: 权威交易日历（P1-01）✅ 完成

### 目标
消除"全 src 无交易日历实现"：数据层提供权威交易日历接口，PIT 面板按真实交易日对齐，停牌日不再产生错误网格。

### 现状（修复前）
- 全 src grep `trade_cal|trade_calendar|is_open` 零命中；`build_earnings_panel`（earnings.py:374）与 `build_quality_panel`（fundamentals_quarterly.py:164）的 `trade_dates` 均由调用方传入。
- 所有 notebook 用 `data["date"].unique()` 从行情推断交易日（如 `strategy_quality_diagnostic.py:100`）。停牌日/节假日缺失 → PIT 面板网格错位。

### 变更
- 新增 `src/data/trade_calendar.py`，三个公开接口（tushare `trade_cal` 为数据源，parquet 缓存于 `data/raw/trade_cal/{exchange}.parquet`，按年分片拉取 [1990-01-01, 2030-12-31] 规避单次行数限制）：
  - `fetch_trade_calendar(exchange="SSE", cache_dir=None)` → DataFrame（exchange, cal_date, is_open, pretrade_date；cal_date 升序无重复；缓存命中校验必需列，缺列抛错；起始日偏晚打 warning）
  - `fetch_trade_dates(start, end, exchange="SSE", cache_dir=None)` → pd.DatetimeIndex（仅 is_open=1，闭区间，升序无重复；start/end 支持 tz-aware 自动归一化）
  - `is_trading_day(date, exchange="SSE", cache_dir=None)` → bool（周末/节假日/不在日历中返回 False）
- `src/data/__init__.py` 导出 `TRADE_CAL_SCHEMA` / `fetch_trade_calendar` / `fetch_trade_dates` / `is_trading_day`。
- 迁移 9 个 PIT 面板消费方（notebooks）：`strategy_quality_diagnostic` / `csi500_continuous_backtest` / `phase15_grid_search` / `csi500_earnings_backtest` / `csi1000_earnings_backtest` / `phase16_backtest` / `rebalance_frequency_sweep` / `phase15_backtest` 的 `trade_dates = pd.DatetimeIndex(sorted(data["date"].unique()))` 改为 `fetch_trade_dates(START_DATE, END_DATE)`；`evaluate_new_factors` 的 `trade_dates`（同时驱动逐日 fundamentals 拉取）改为 `list(fetch_trade_dates(START_DATE, END_DATE))`。
- **范围确认（用户拍板）**：回测引擎（engine.py）与 walk-forward/continuous 的日期切分逻辑保持现状（仍以实际行情日期为准），不动"最稳定组件"；Notebooks 中仅统计用途的 `date.unique()` 打印保留。
- **Review 加固**：单次全量拉取改按年分片（41 次请求）——规避 tushare 单次行数限制导致残缺日历被静默永久缓存的隐患；缓存命中校验 schema 列 + 起始日覆盖软校验；`is_trading_day`/`fetch_trade_dates` 对 tz-aware 输入归一化。

### 测试
- 新增 `tests/data/test_trade_calendar.py`（19 tests）：schema/dtype/升序去重 / 缓存命中不重复调 API / 按年分片参数透传 / 缓存 dtype 契约（读回 datetime64+int）/ 坏缓存缺列报错 / 缺 token 报错 / 空返回不写缓存 / 只返回 is_open=1 / 闭区间截取 / 区间无交易日 / start>end 空 / 无参全量 / tz-aware 边界 / is_trading_day / tz-aware 判断 / 空日历返回 False / **PIT 网格对齐**（节假日+周末不出现在 build_earnings_panel 网格——P1-01 核心修复验证）。
- 单元 890（+19）+ 管道 26 = 916 tests 通过；`ruff check src/` 无新增问题（存量 65 个 lint 错误未触碰，遵循最小改动原则）；`ruff format --check` 通过。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | 数据源用 tushare `trade_cal` + parquet 缓存 | 与项目数据栈/缓存/测试模式一致，覆盖未来日期；用户拍板（备选 exchange_calendars 离线库未选） |
| 2026-06 | 接入范围=日历接口 + PIT 面板消费方 | 用户拍板最小范围；回测引擎为"最稳定组件"不动，回测结果零变化 |
| 2026-06 | 按年分片拉取并缓存 [1990-2030] 全量 | 交易日历为静态低频数据，全量缓存免增量逻辑；按年分片规避 tushare 单次行数限制导致的静默截断（review 加固）；覆盖历史回测与"今天是否交易日"判断 |
| 2026-06 | 沪深取 SSE 交易所 | 项目已排除北交所，沪深节假日一致；exchange 参数保留扩展性 |

### 已知环境问题
- `TUSHARE_TOKEN` 当前已过期（tushare 返回 "token已过期"）：`tests_integration/` 8 个用例失败，与本 Phase 无关（未改动任何 tushare 调用路径）；token 恢复后即可运行。`fetch_trade_calendar` 的真实数据验证同样依赖 token 恢复。

---

## Phase 20: 因子注册表收口 + 结果缓存（2026-06）

### 目标
消除"24 个已实现因子未注册、策略直接 import 绕过注册表"的口径脱节；因子计算结果可缓存复用。

### 现状（修复前）
- `FACTOR_REGISTRY` 值类型锁死为 `Callable[[DataFrame], Series]`，无法表达带参因子；55 注册条目 = 32 唯一因子 + 23 别名。
- 24 个已实现因子未注册：volatility_gtja（5）、mean_reversion（4）、trend（3）、vwap（2）、volume_price（4，其中 3 个带 window 参数）、volatility（1，带 window）、cointegration（5，配对专用签名）。
- 13 个策略文件直接 import 因子函数绕过注册表；同一因子（如 calc_rsi / calc_volume_ratio）在多个策略中重复计算，无任何存储/缓存。

### 变更
- **注册表契约扩展**（registry.py）：条目升级为 `FactorSpec`（func/tags/kind/params）；`kind` 支持 "single" / "pair"；默认参数从函数签名自动提取（`window` 等），`run_factor(name, df, **params)` 支持 kwargs 覆盖；`get_factor` 仍返回原始函数（向后兼容）；`list_factors(tag, kind)` 支持类型过滤；`calc_factors` 支持按因子名透传参数（`params={"calc_hv": {"window": 60}}`，落实 data-schemas 的"参数无关设计"）。
- **新增缓存设施**（cache.py）：磁盘 parquet 缓存，路径 `data/factors/{因子名}/{参数哈希}_{数据指纹}.parquet`；缓存键 = (因子名, 参数哈希, 数据指纹)，调参/数据变化不串缓存，指纹与行顺序无关；原子写；`clear_factor_cache` 清理；`FACTOR_CACHE_DIR` 环境变量覆盖默认目录（测试经 conftest 隔离到 tmp）。
- **注册 24 个因子**：19 个 single（volatility_gtja 5 / mean_reversion 4 / trend 3 / vwap 2 / volume_price 4 / volatility 1）+ 14 个 GTJA 编号别名（gtja_21/63/78/79/89/97/100/112/116/120/124/128/161/175）+ 5 个 pair。注册表口径 = 实际可用因子集：93 条目（51 single primary + 5 pair + 37 别名）。
- **策略层 13 个文件改走注册表**（唯一因子入口）：无参因子 `run_factor(name, df)`、带参因子透传 window、pair_trading 经 `get_factor` 取函数、`_FACTOR_COMPUTERS` / `FACTOR_COMPUTE` 映射改为注册名；`rg` 确认无残留 factors direct import（仅 registry / neutralize）。
- 决策（用户拍板）：cointegration 进注册表但按 pair 类型管理（按名可发现，不参与 run_factor）；缓存用磁盘 parquet（跨进程/跨回测复用）。

### 测试
- 新增/更新 `tests/factors/test_registry.py`（41 tests）：FactorSpec 契约、参数自动提取、run_factor 透传与 pair 拒绝、calc_factors 参数透传、kind 过滤、**全口径守卫**（注册集 == 实现集 93 条目，防新增因子漏注册）、新增 19 因子冒烟。
- 新增 `tests/factors/test_factor_cache.py`（7 tests）：命中不重算、参数区分、数据区分、结果对齐、禁用重算、清理、NaN 往返。
- 新增 `tests/conftest.py` / `tests_pipeline/conftest.py`：autouse 将 `FACTOR_CACHE_DIR` 隔离到 tmp，避免测试污染 `data/factors/`。
- 单元 913 + 管道 26 = 939 tests 通过；`ruff check` 本次新增文件零错误（存量 24 个 lint 错误均为预存在，未触碰）；`ruff format --check` 通过。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | cointegration 5 个配对因子进注册表但用 kind="pair" 管理 | 用户拍板；按名可发现、口径完整，但签名不兼容 run_factor，由调用方按配对接口直接调用 |
| 2026-06 | 缓存用磁盘 parquet（data/factors/） | 用户拍板；跨进程/跨回测复用，符合项目 parquet 存储习惯与分块约束 |
| 2026-06 | 新增 GTJA 编号因子一并注册编号别名（gtja_21 等 14 个） | 与 momentum / volume_price_gtja 既有别名模式一致，按编号统一发现 |
| 2026-06 | `get_factor` 保持返回原始函数 | 兼容红线：策略与既有测试依赖"返回可调用对象"，契约扩展不破坏现状 |
| 2026-06 | `run_factor` 返回 Series 统一 name=因子名 | 缓存命中路径（列名 value）与计算路径（继承输入列名）的 name 不一致，统一后两次调用完全相等 |

### 已知环境问题
- 系统 python3（pandas 3.0）下 `tests/factors/test_neutralize.py::test_demean_with_real_like_data` 失败（datetime64 us vs ns 断言），为 pandas 3.0 行为变更所致，与本 Phase 无关；项目真实环境 `.venv`（pandas 2.3.3）下全量通过。

## Phase 21: 因子评估设施 IC/IR + 分层回测（P1-05，2026-06）

### 目标
提供可复用的标准因子评估工具（IC/IR、forward return、分层回测），取代临时 notebook 脚本（`notebooks/evaluate_new_factors.py`），使评估结果可复现、可比较。

### 现状（修复前）
- 全 src 无任何 IC/IR 计算：`per_period_ir`（`src/backtest/walk_forward.py:128`）是策略 per-period Sharpe 的 mean/std（回测一致性 IR），非因子 IC；`stock_selector.evaluate_factors` 是 coverage/stability/dispersion 质量审计，也非 IC/IR。
- 因子评估仅存在于 `notebooks/evaluate_new_factors.py`：walk-forward 组合回测 + 因子间相关矩阵，无相关系数、无分层收益，结果不可复现不可比较。

### 变更
- **新增 `src/factors/evaluation.py`**（纯 DataFrame 输出，不依赖交易管线与绘图库）：
  - `compute_forward_returns(price_df, windows=(1,5,20), exclude_untradable=False)`：按 code 分组的 N 数据行前向收益率（复用 `pipeline_diagnostics.forward_return_analysis` 模式），返回与输入逐行对齐；exclude 时涨跌停/停牌行置 NaN。
  - `compute_ic(factor_df, name, fwd_ret, method="spearman", min_obs=5)`：每日截面 IC 时序（默认 RankIC，pandas `Series.corr` 实现，**无 scipy 直接依赖**）；有效样本 < min_obs 的日期跳过。
  - `compute_ir(ic_series)`：IR = IC 均值 / IC 标准差（ddof=1）；<2 值 NaN，IC 恒定（std=0）返回 inf。
  - `compute_quantile_returns(factor_df, name, fwd_ret, n_quantiles=5, rebalance_days=None)`：每日截面 rank 分位分层等权组合，输出 `quantile_returns`（q1..qn 宽表）/ `summary`（mean/std/hit_rate）/ `long_short`（qn-q1 价差）；`rebalance_days=N` 每 N 数据行取一个调仓日（与 `pipeline.py` 同款语义）。
  - `evaluate_factor(...)`：一站式，输出 `{ic, ic_series, quantiles}`。
  - `evaluate_factors(factor_df, names, ...)`：批量比较表 `[factor, window, ic_mean, ic_std, ic_ir, ic_positive_ratio, ls_mean, ls_ir]`，每因子每窗口一行，作为策略开发的标准筛选环节。
- 输入约定与 `calc_factors` 宽表输出兼容：任意行序（内部排序计算后映射回输入顺序）；`price_df` 省略时从 `factor_df` 的 close 列取。
- 决策（用户拍板）：模块落点 `src/factors/evaluation.py`（P1-05 归属 factors）；IC/分层默认不剔除涨跌停/停牌（纯预测力口径），提供 `exclude_untradable` 参数按需剔除；纯 DataFrame 输出不引入 matplotlib。

### 测试
- 新增 `tests/factors/test_evaluation.py`（27 tests）：forward return 基本/多窗口/乱序输入对齐/exclude 剔除/缺列报错；IC 完美正负相关（≈±1）/噪声近零/min_obs 过滤/NaN 行剔除/pearson/index 排序/缺列报错；IR 边界（空/单值/恒定）；分层收益单调性/多空价差符号/rebalance 采样/二分/样本不足报错；evaluate_factor 结构/price_df 省略；evaluate_factors 批量表结构与值正确。
- factors 目录 294 tests 通过；全量单元 + 管道预计 ~968 tests（最终数字以验证为准）。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | 模块落点 `src/factors/evaluation.py` | 用户拍板；P1-05 归属 factors，与 run_factor/calc_factors 天然衔接，测试归 tests/factors/ |
| 2026-06 | IC 默认不剔除涨跌停/停牌样本 | 用户拍板；评估纯预测力（学术口径），`exclude_untradable` 参数按需剔除 |
| 2026-06 | 纯 DataFrame 输出，不引入 matplotlib | 用户拍板；结构化输出最易复现比较，图表另走 visualization 层 |
| 2026-06 | 用 pandas `Series.corr(method="spearman")` 而非 scipy | scipy 仅为 statsmodels 传递依赖，未显式声明；pandas 原生实现免新增直接依赖 |
| 2026-06 | forward return 沿用"N 数据行"口径 | 与 `pipeline_diagnostics` 全库统一；交易日历感知的持有期收益留待后续增强 |
| 2026-06 | 返回与输入逐行对齐 | 与 run_factor 契约一致，调用方无需自行排序，杜绝乱序错位 |

### 已知环境问题
- 与 Phase 20 相同：系统 python3（pandas 3.0）下 `test_demean_with_real_like_data` 失败为预存在环境差异，`.venv`（pandas 2.3.3）下全量通过。

## Phase 22: 命令行工具 yq + import 口径统一（2026-06）

### 目标
1. 解决"IC/IR 等模块功能无统一 CLI 调用入口"（用户提出）：所有能力只能通过 24 个 `notebooks/*.py` 脚本各自硬编码调用。
2. console script 暴露的 import 口径问题：项目内部用 `from src.xxx import`，但 editable 安装把 `src/` 目录映射进 sys.path（顶层导入），导致从任意 cwd 运行时 `import src.factors` 失败。

### 变更
- **新增 `src/yq/` 包**（typer 0.27，pyproject 新增依赖 + `[project.scripts] yq = "yq.cli:app"`）：
  - `yq factor list [--tag] [--kind]`：注册表查询（name/kind/tags/params）
  - `yq factor run NAME --input x.parquet [--param k=v ...] [--output] [--no-cache]`：单因子计算（复用 `run_factor`，结果与输入逐行对齐）
  - `yq factor evaluate --input f.parquet [--price] --factor X ... [--window] [--method] [--quantiles]`：IC/IR + 分层批量比较表（复用 `evaluate_factors`）
  - `yq cache info/clear [--factor] [--cache-dir]`：磁盘缓存统计与清理
  - `src/yq/output.py`：统一渲染层，默认文本表格、`--json` 输出合法 JSON（NaN/NaT/inf → null）
  - 双入口：`python -m yq`（`__main__.py`）+ console script `yq`
- **import 口径统一（全项目重构）**：`from src.xxx` / `import src.xxx` / mock patch 字符串 `"src.xxx"` 共 462+ 处全部改为顶层导入（`from factors.registry` 等），覆盖 src/ tests/ tests_pipeline/ tests_integration/ notebooks/。根因：editable finder 将 src 目录直接映射进 sys.path，`src.` 前缀只在 cwd=项目根 时可用；而 console script 从任意 cwd 运行必然失败。统一后与安装形态（wheel 顶层包）天然一致。
- **pyproject**：dependencies + `typer>=0.12`；新增 `[project.scripts]`。
- **文档**：README 新增"命令行工具（yq）"章节 + 数字修正（93 条目、1007 tests）；project-plan 状态表与目录树更新；infrastructure-todo P2-07（README 数字过时）完成。

### 测试
- 新增 `tests/cli/`：test_output.py（渲染层 NaN→null/ISO datetime/空表）、test_cli.py（help/version/未知命令冒烟）、test_factors_cmd.py（list 过滤与 JSON、run 对齐/参数/输出 parquet/pair 拒绝/未知因子、evaluate IC≈1/多因子/无 price 回退/missing column）、test_cache_cmd.py（info 统计/clear 全部与单因子）。
- typer 0.27 适配：`no_args_is_help` 与 eager callback 交互变化 → 改 `invoke_without_command=True` + `ctx.get_help()`；`Typer` 无 `get_help` 方法。
- 错误消息走 stderr（`err=True`）+ exit code 1；typer 0.27 下 `--version` 需 eager option + callback 提前 `raise typer.Exit()`。
- 全量：**1007 passed**（单元 + 管道），ruff 全量 errors 从 537（基线）降至 388（全部为预存在 E501/E402/F841）。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | 首批子命令 = 只读查询 + 评估（factor list/run/evaluate + cache info/clear） | 用户拍板；无需 token 立即可用，验证入口骨架后再扩 pipeline |
| 2026-06 | CLI 框架用 typer | 用户拍板；类型注解驱动，pyproject 新增依赖 |
| 2026-06 | `python -m yq` + console script `yq` 双入口 | 用户拍板；任何环境可跑 + 安装后短命令 |
| 2026-06 | 文本表格 + `--json` 双输出 | 用户拍板；终端可读 + 脚本/notebook 消费 |
| 2026-06 | 全项目统一顶层导入（462+ 处） | 用户拍板；与 editable/wheel 安装形态一致，console script 任意 cwd 可用，一次修净 |
| 2026-06 | 数据输入显式 `--input parquet` | `data/clean/` 为空且 notebooks 各自加载；不绑死目录，灵活可复现 |
| 2026-06 | 错误消息走 stderr + exit 1 | 标准 CLI 行为，stdout 留给数据输出（管道友好） |

### 已知环境问题
- 与 Phase 20/21 相同：系统 python3（pandas 3.0）下 `test_demean_with_real_like_data` 失败为预存在环境差异，`.venv`（pandas 2.3.3）下全量通过。

## Phase 23: yq factor list --verbose + IC/IR 筛查脚本（2026-06）

### 目标
用户提出：CLI 已有入口后，直接测试各因子 IC/IR；在 notebooks/ 建可复用脚本——列出当前因子及介绍、展示单一因子与多因子批量比较表。

### 变更
- **`yq factor list --verbose`**：新增 `--verbose` 选项，追加 `description` 列（因子函数 docstring 首行，`inspect.getdoc`）；别名与主因子共享同一函数 → 介绍一致。默认输出不变（避免表格变宽），`--json` 同理。
- **`notebooks/icir_factor_screening.py`**（可复用，subprocess 调 `python -m yq`）：
  1. `yq factor list --verbose`：全部注册因子 + 介绍
  2. 数据：`--data path.parquet` 用真实行情（校验 date/code/close）；缺省生成合成行情（30 股 × 250 交易日，收益 = beta*s_i + 噪声，s_i 为每股隐藏 alpha → 价格派生因子动量/OBV/RSI IC 显著、纯量 volume_ratio IC≈0），参数化文件名缓存（`synthetic_ohlcv_{n}_{d}_{seed}.parquet`），每次清理中间因子产物
  3. 单一因子：`yq factor run` → `yq factor evaluate`（1/5/20 窗口 IC 均值/IC_IR/分层多空）
  4. 多因子批量：因子 parquet 按 (date, code) 拼面板 → `yq factor evaluate` 比较表（5 日窗口，每因子一行）
- 参数：`--factor`（可重复，缺省演示集 6 个）、`--n-stocks/--n-days/--seed/--no-cache`。

### 测试
- `tests/cli/test_factors_cmd.py` +3：verbose 文本含 description/OBV、verbose JSON 有 description 且别名与主因子一致、默认 JSON 无 description。
- 冒烟：脚本端到端跑通；合成数据（beta=0.02）下动量/OBV/RSI 等价格派生因子 IC 0.5-0.93（窗口越长越显著）、calc_hv 负 IC（-0.05~-0.08）、calc_volume_ratio（纯量）IC≈0。价格派生因子普遍显著是合成强动量结构的自然结果，文案已如实标注。
- 全量 **1012 passed**，ruff 干净。

### 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06 | 因子介绍由 CLI 提供（`factor list --verbose`），非脚本内 import | 用户拍板；口径统一，脚本纯调 CLI |
| 2026-06 | 合成数据为主 + `--data` 换真实 | 用户拍板；data/clean 为空且 token 过期，脚本开箱即用且可复现 |
| 2026-06 | 合成收益 = beta*s_i + 噪声（beta=0.02） | 截面 alpha 结构让价格派生因子（动量/OBV/RSI）IC 显著正、纯量（volume_ratio）≈0、波动率负，形成对照；docstring 注明合成 IC 偏大属正常 |

## Phase 24: 全市场日 K 拉取与清洗（2026-08）

### 背景
用户需求：拉取全市场近 3 年日 K，清洗后必须含 limit_up / limit_down / is_suspended 三列。

### 变更
- **fetcher.py 保留 pre_close**：`fetch_daily` / `fetch_index_daily` / `fetch_daily_batch` 返回列增加 `pre_close`（tushare 官方前收，除权除息日已调整）。`OHLCV_SCHEMA` 不变（pre_close 为附加列，`validate_ohlcv` 只查必需列）。
- **fetcher.py 瞬时错误重试**：`fetch_daily` 重试条件从仅限流（"过快/频率"）扩展到 `unavailable`/`timeout` 等 proxy 瞬时错误，退避 2s/4s、最多 3 次；token 错等确定性错误不重试直接抛。
- **filters.detect_limit_price 两处修正**：
  1. 前收盘优先取 `pre_close` 列（缺失回退 shift(1)，兼容旧调用顺序）；修复除权除息日 shift(1) 误判涨跌停的问题
  2. 涨跌停幅度按板块区分：创业板/科创板（300/301/302/688/689 前缀）20%，其余取 `limit_pct`（默认 10%）；ST/北交所由上游股票池排除
- **filters.detect_suspension 停牌网格补齐**：volume==0 规则保留；新增按交易日网格补齐缺失交易日（tushare daily 对停牌日无记录），补齐行 OHLCV/pre_close=NaN、is_suspended=True、已有 limit 列填 False；下界裁剪到股票首行日期（上市日前不补），上界不裁剪（股票池为当前上市股票，停牌至今需补到网格上界）；`trade_dates=None` 时用 df 内所有股票 date 并集推断网格。
- **新增清洗入口 `data/clean.py: clean_market_data(df, trade_dates=None)`**：detect_suspension → detect_limit_price 一步完成三列标注，输出按 (code, date) 排序、无重复行。
- **trade_calendar.py proxy 修复**：`_PROXY_URL` 从失效的 `http://124.222.60.121:8020/` 改为 `https://quantdata888.duckdns.org`（与 fetcher 一致，实验验证 trade_cal 可用）。注：`earnings.py` / `fundamentals_quarterly.py` 仍用旧失效 proxy，不在本次拉取链路中，待后续处理。

### 测试
- test_filters +7：除权日 pre_close 不误判、无 pre_close 回退 shift、板块 20%/10% 幅度、停牌网格补齐、上市日前不补、并集推断、limit 列保留
- test_fetcher 改 2 + 加 3：列断言改子集 + pre_close 映射 + fetch_index_daily pre_close + 瞬时错误重试 + token 错误不重试
- test_clean 新增 5：三列 bool、停牌补齐、排序去重、涨停检测
- 全量单测 **1000 passed**、管道测试 **26 passed**，ruff 干净（earnings.py 既有 8 个 E501 未动）

### 数据工程
- `notebooks/fetch_full_market.py`：`fetch_all_stocks`（5329 只）→ `fetch_daily_batch`（`data/raw/full_market_3y/`，独立目录避免污染旧 10 年无 pre_close 缓存）→ `fetch_trade_dates` → `clean_market_data` → `data/clean/full_market_ohlcv.parquet`
- 范围 2023-08-06 ~ 2026-08-05（近 3 年）
- duckdns proxy 偶发瞬时 "service temporarily unavailable"（trade_cal 与日 K 均遇到），靠新增重试自愈

### 并发加速（同 Phase 24 补充，2026-08）
- **`fetch_daily_batch` 新增 `workers` 参数**（默认 1 = 串行，行为不变；>1 用 `ThreadPoolExecutor` 并发，每 worker 每次 API 调用后 sleep `sleep_sec`）。任一只股票失败抛异常、已缓存保留（断点可续）；按股票分文件缓存天然无并发写冲突。
- **测试**：test_fetcher +2（并发 3 worker 每 worker sleep 1 次共 3 次、失败传播）；默认串行测试不变。全量单测 **1002 passed**。
- **验证**：真实 proxy 10 workers × 20 只 17.5s（0.88s/只，较串行 ~4-5s/只 快 ~5 倍），无失败。
- **全量拉取**：`notebooks/fetch_full_market.py` 改用 `workers=10`（用户 15000 积分确认，proxy 无限流）。用户确认后由串行（预计 ~10h）切换为并发（预计 ~1.5h）。

### 全市场拉取完成 + 北交所 920 修复（同 Phase 24 补充，2026-08）
- **发现并修复 bug**：`fetch_all_stocks` 北交所排除逻辑 `startswith(("8","4"))` 漏掉北交所 920 新代码段（2024 年后启用，330 只漏网）。改为 `startswith(("8","920"))`，TDD 补测试（920 股票断言排除）。test_fetcher 28 passed。
- **并发参数演进**（proxy duckdns 在持续并发下劣化，实测各组合）：10w/0.3s → 6w/0.3s → 8w/1s → 4w/2s。4+2 在劣化期净速度最优（~19 只/分钟 vs 8+1 的 11 只/分钟，重试大幅减少）。
- **最终数据**：`data/clean/full_market_ohlcv.parquet`，**4999 只 A 股（排除 ST/北交所）**、**3,540,684 行**（3 年：2023-08-07 ~ 2026-08-05，726 交易日）、55.6MB。列：date/code/open/high/low/close/pre_close/volume + limit_up/limit_down/is_suspended（均 bool，无重复 (date,code)）。
- **三列统计**：limit_up=28,114、limit_down=7,525、is_suspended=4,207（补齐停牌日行，close/pre_close=NaN）。
- **proxy 劣化期 6 只股票重试耗尽缺数据**（603590/603708/603899/603900/605337/605338），已逐个补拉（各 726 行），其中 603900/605338 曾连续空响应，最终补齐。
- 原始缓存：`data/raw/full_market_3y/{code}.parquet`（4999 个，含 pre_close；920 北交所缓存已删除）。

## Phase 25: 因子生命周期监控（2026-08-05）

### 决策记录
- **形态**：一次性筛查升级为**持续监控**——游资因子有效窗口 2-8 个月，监控支撑"因子失效就换"决策
- **数据范围**：全市场（除北交所/ST），近 3 年（AI 量化普及因子衰减加速，"时间太长反而找不出好因子"）；监控系统按日频交易设计，评估在日级尺度统计
- **判定双轨**：滚动 t 统计量为主（|t|>2 活跃、<1 失效、中间维持），0.7/0.3 IR 仅作绘图参考线——因 IR×√window≈t，60 日窗口 IR=0.7↔t≈5.4 几乎无因子达到、0.3↔t≈2.3 几乎全因子低于，区分度差，不能作判定阈值
- **防抖**：连续 ≥20 交易日（min_sustain）才切换状态，防止噪声抖动
- **因子范围**：`list_factors(kind="single")` 动态发现全部量价 single 因子（88 个），不硬编码列表
- **增量策略**：state 长表持久化，每次只重算 `last_date - window - 因子 lookback 缓冲` 之后的尾部；`--full` 全量重算（冷启动/阈值校准）。2 年数据全量首跑分钟级，尾部增量秒级
- **模块边界**：滚动原语放 `factors/evaluation.py`（纯函数，与 `compute_ic` 输出 Series 直接 rolling）；状态机/持久化/编排在 `analysis/factor_monitor.py`；不抽公共滚动层、不与 `walk_forward.generate_windows`（train/test 回测窗口语义）耦合

### Task 0：数据修复前置（涨跌停标注错误会污染 IC）
- **北交所过滤回归**：`startswith(("8","4"))` 漏掉 920 新代码段 → 改 `("4","8","920")` + market 列兜底
- **涨跌停精度**：价格比较改 `np.round(prev_close*(1±pct), 2)` 到分（原直接乘 10%/20% 导致 5.025 类奇数分前收漏判）
- **停牌补齐上界**：补齐裁剪到 `min(网格上界, df 内最大日期)`，不再越过最后数据日
- **清洗入口**：`data/clean.py: clean_market_data`（detect_suspension → detect_limit_price）
- **proxy 修复**：`_PROXY_URL` 统一 HTTPS duckdns；`notebooks/test_tushare.py` 密钥改环境变量注入（硬编码密钥从源码移除）
- 重清洗后标注大幅修正：limit_up 28,114→**44,661**、limit_down 7,525→**13,543**
- 全量 **1011 passed + 26 pipeline passed**

### Task 1：滚动评估原语（factors/evaluation.py，TDD +12 tests）
- `compute_rolling_ic(ic_series, window, min_periods=None)`：滚动 IC 均值
- `compute_rolling_ir(...)`：滚动 IR = 滚动均值/滚动标准差（ddof=1；std=0 → inf，与 `compute_ir` 一致）
- `compute_rolling_tstat(...)`：t = IR × √n（n=窗口内有效样本数），与窗口长度解耦，是状态机判定主输入

### Task 2：状态机 + 持久化 + 编排（analysis/factor_monitor.py）
- 状态机 `run_state_machine`：active/decaying/dead/reverse 五态（含 t 反向显著 → reverse），sustain_days 防抖
- 持久化：`state.parquet`（9 列长表 `(date, factor, fwd_window)`，运行前备份 `state.bak.parquet`）、`changes.parquet`（`(date, factor, fwd_window, old_state, new_state)`，无切换不落盘）
- `run_monitor` 编排：动态发现 single 因子 → 尾部增量窗口（`last_date - window - lookback 缓冲`）→ 滚动统计 → 状态机 → diff → 落盘
- 管道测试：增量语义（续跑只重算尾部、旧尾部同值不重复切换）、多因子独立性、全链路 schema

### Task 3：yq factor monitor CLI（yq/factors.py + yq/monitor.py）
- 参数：`--data/--factor/--windows(默认5)/--window(60)/--min-sustain(20)/--min-obs(5)/--t-active(2.0)/--t-decay(1.0)/--ir-active-line(0.7)/--ir-dead-line(0.3)/--full/--no-cache/--output-dir/--json`
- 状态摘要表（每 factor×fwd_window 一行，dead 置顶）+ 本次状态切换 diff
- **端到端验证**（全市场 4999 股 × 近 3 年，calc_hv fwd=5 window=60）：首跑 **3.7s**、增量第二次 **1.9s**；state 701 行（726 交易日 - 20 lookback - 5 fwd）2023-09-04→2026-07-29；calc_hv 判 dead（最新 t=-3.59，2026-05-26 进入，负 t 说明 HV 当前为反向因子）

### Task 4：绘图（analysis/plot.py）
- `plot_factor_lifecycle`：双轴——左轴滚动 IR（+0.7/0.3 参考线）、右轴 t 统计量（+±2/±1 判定线）；背景按状态着色（active 绿/decaying 黄/dead 红/reverse 灰蓝）
- `plot_factor_health_heatmap`：x=时间、y=因子（factor×fwd_window）、颜色=滚动 IR（RdYlGn 对称截断 5/95 百分位、NaN 浅灰）
- CLI 保存 `figures/health_heatmap.png` + 每 (factor,fwd) 一张 lifecycle PNG（Agg 后端，`--json` 输出 figures 键）

### 测试与提交
- 全量单测 **1053 passed**（+滚动 12 + monitor 16 + plot 11 + CLI monitor 9 等），ruff 干净（既有 test_earnings/test_storage E501 未动）
- commits：`02af806`(北交所)→`71ef66a`(涨跌停精度)→`7d158ae`(停牌上界)→`a656ac0`(限频)→`1a04a43`(密钥)→`4717d07`(幂等)→`ee803b9`(downcast)→`654b3de`(清洗管道)→`afba929`(fetch 脚本)→`62d993d`(文档)→`cefc7e8`(print 格式)→ Task1..4 逐步提交，本 Phase 收尾 `8180aa4`
- 剩余：Task 6 全量首跑（88 single 因子）+ 阈值校准（未开始）

### Task 6：全量首跑 + 阈值校准（2026-08-05，补充）
- **命令**：`yq factor monitor --data data/clean/full_market_ohlcv.parquet --full --output-dir data/audit/factor_monitor_full`
- **结果**：80 个量价因子 × fwd=5 × window=60，state 长表 56,822 行（2023-08-07 → 2026-07-29）；跳过 8 个缺列因子（fundamental 透传：earnings_surprise/acceleration/ep/bp/roe_level/roe_stability/cashflow_quality + turnover 缺 total_mv；amihud 用 volume 代理可算，未跳过）
- **运行发现并修复**：`calc_earnings_surprise` 等透传因子直接读 df 同名列 → KeyError 中断整批；`run_monitor` 改为循环内捕获 KeyError 跳过并返回 `(state, skipped)`，CLI stderr 汇总提示（TDD +1 测试）
- **最新状态分布**（2026-07-29）：dead 60 / reverse 7 / decaying 5 / **active 8**——active 全为 GTJA 量价相关类：calc_close_vol_rank_cov_5d(gtja_99, t=+4.49, sustain 613 天)、calc_high_vol_rank_corr_3d(gtja_32, t=+4.10)、calc_vwap_vol_rank_corr_5d(gtja_90, t=+4.00)、calc_vol_rank_intraday_corr_6d(gtja_1, t=+1.84)
- **阈值校准结论**：
  - t 判定线（±2 活跃 / ±1 失效）**有效**：最新 |t|>2 占 45%、|t|<1 占 37.5%，区分度良好
  - IR 参考线 0.7/0.3 **维持默认**（仅绘图）：最新全因子 |IR|<0.7（max 0.579，0 个达到 0.7）、|IR|<0.3 占 60%——印证设计预判（IR×√window≈t，IR 线区分度差），不做判定线
  - 全历史状态占比：reverse 47.3% / dead 34.3% / active 17.3% / decaying 1.2%；全历史 t 中位数 -1.93、IR 中位数 -0.25——近 3 年全市场量价因子整体偏反向（散户主导市场的常见特征）
  - **默认阈值保持不变**：--t-active 2.0 / --t-decay 1.0 / --ir-active-line 0.7 / --ir-dead-line 0.3
- **产出**：`data/audit/factor_monitor_full/state.parquet`（1.35MB）+ `figures/`（heatmap + 80 张 lifecycle PNG）
- 全量单测 **1054 passed**，ruff 干净

## Phase 26: factors 目录分层重构（2026-08-06）

### 决策记录
- **动机**：`src/factors/` 扁平化，因子实现 / 算子原语 / 元功能（评估、中性化、缓存、调度）混杂同一层 19 个文件；且 Phase A/B/C 因子清洗（factors-clean 设计）需要明确归属
- **分层原则**：每层只依赖下层，无反向依赖。顶层只留调度（registry）与算子原语（operators）；因子实现进 `factors/builtin/`（13 个，只依赖 operators + pandas，命名对齐 strategies/builtin/ 先例）；对因子的操作进 `factors/ops/`（evaluation / neutralize / cache 迁入，Phase A/B/C 的 correlation/oos/synth 后续落这里）
- **设计修订（吸收审阅意见）**：Phase A/B/C 的清洗操作属于"对因子的操作"，放 `factors/ops/` 而非 analysis 层；analysis 只保留业务编排（factor_monitor）
- **关键技术事实**：`from factors.evaluation import X` 无法靠 `__init__.py` 属性兼容（CPython 对 `from A.B import C` 不 fallback 到包属性）→ 子模块路径 import 全量更新，`__init__.py` 只保证顶层 re-export（`from factors import compute_ic`）
- **磁盘缓存不失效**：run_factor 缓存 key 按因子名（非模块路径），迁移后命中不变

### 影响面（实测）
- factors 内部 19 个 `.py` = 顶层 3 + builtin 13 + ops 3；registry 内部 14 处 import（模块级 cache×1 + 函数内延迟 import 13 因子）
- src/ 外部 import 18 文件（12 个需改子模块路径，6 个只 import registry/operators 不动）；tests 15 文件需改

### 执行（TDD，5 task）
- **Task 1**：`tests/factors/test_layering.py` 分层锚点（builtin/ops 可导入 + 顶层 re-export）失败先行 → `f20d6c8`
- **Task 2**：git mv 16 文件（13 因子 → builtin/，3 操作 → ops/），全部 100% rename 可追溯 → `f8e0587`
- **Task 3**：重写 `__init__.py` + 修正 registry 内部 import → 93/88 保持，layering+registry 30 passed → `a411165`
- **Task 4**：批量替换外部 import（src 12 + tests 15 文件）零残留 → 全量 1058 + 30 pipeline → `4dc1a80`
- **Task 5**：ruff 清理本任务引入的 5 处（__init__/registry/test_quality 的 I001 + E501，--fix 折行）；契约文档同步（factors-clean §3.4 实测数据、data-schemas 路径、project-plan 状态表+目录树）；存量 27 处 ruff 错误（builtin 内部 E501/N806、engine/test_pipeline 业务行）按先例不碰
- 最终验收：`list_factors()` 93（single 88 / pair 5）不变；`from factors import compute_ic` 可用；全量 1058 单测 + 30 pipeline 绿；git 历史 16 rename

## Phase 27: 因子相关性去冗余 Phase A（2026-08-06）

### 决策记录
- **动机**：全量首跑（Phase 25 Task 6）最新 8 个 active 因子全部集中在 GTJA"价格-成交量相关"类——calc_close_vol_rank_cov_5d / calc_high_vol_rank_corr_3d / calc_vwap_vol_rank_corr_5d / calc_vol_rank_intraday_corr_6d 的 t 与持续天数高度同步，本质是同一信号在不同窗口下的写法（数学上高度共线）。单因子有效 ≠ 组合有效，需先做因子间相关性检查（去冗余）
- **相关口径（主）**：**因子值截面 rank 相关**——每天全市场按因子值算 spearman 秩相关，再对时间取均值（窗口 60 交易日，与 monitor 一致）。理由：组合真正冗余的是"持仓重叠"（每天排同一批股票），不是 IC 是否同向
- **相关口径（辅）**：IC 时序相关仅作辅助诊断，不做判定（两个因子 IC 时序低相关反而可能是互补，那是组合要追求的）
- **候选范围**：仅 active / decaying 因子（dead/reverse 已判无效，不参与组合），且 fwd_window 匹配
- **冗余阈值**：默认 |ρ| > 0.7 判冗余（可在 `configs/factor_clean.yaml` 调整）
- **聚类语义**：距离 = 1 − |ρ|，scipy ward 层次聚类，距离空间阈值 1−threshold 剪枝；NaN 距离按 1.0（视为不相关）。**连通分量语义落在 ward + distance 剪枝上**（不是显式连通分量：ward 合并代价不等于成对 ρ 上限，簇语义以测试锚点为准）
- **代表因子**：每簇取 t_stat / ir / combined（两维 rank 均值）得分最高者；并列取字典序小者。rank 是全局而非簇内（保序性下两种语义结论一致，按全局 rank 定稿）
- **兼容（配置加载）**：既有 `load_config` 强校验 strategies/risk 段，不适合清洗配置 → **新增 `load_factor_clean_config`**（缺省合并 + 4 项校验：corr_threshold ∈ (0,1)、corr_window 正整数、cluster_linkage ∈ {ward,complete,average,single}、representative_by ∈ {t_stat,ir,combined}）；CLI 优先级：显式参数 > config > 内置默认
- **clusters 形状**：裁定为 **list of dicts**（`{cluster_id, representative, members}`），计划 Interface 行的 `[[cid, rep, members]]` 为笔误，已修正
- **模块边界**：纯函数放 `factors/ops/correlation.py`（无状态、不依赖交易管线），业务编排放 `analysis/factor_clean.py`（只读 monitor 的 state 长表 + 因子值缓存，不重算 IC/状态）

### 执行（TDD，6 task）

- **Task 1**：`compute_corr_matrix`（窗口尾部取最近 N 个交易日 → 逐日截面 spearman → 按 agg 聚合；min_obs 低于阈值跳过当日；对角 1.0，数据不足 NaN）+ 6 tests → `8d5c3fd`
- **Task 2**：`cluster_redundant`（scipy linkage + fcluster distance 剪枝；单因子直接返回簇 0）→ **plan-bug 修正**：计划内 3×3 阈值单调测试矩阵数学矛盾（c 距离 1.0 无法并簇），最小修正为 2 因子矩阵，意图保留 → `bf0794d`
- **Task 3**：`select_representative`（按 by 打分 rank，全局 rank）→ **plan-bug 修正**：brief 参考实现 `rank(na_option="bottom")` 对 NaN 返回最大 rank，会选中 NaN 因子；改为源列 NaN 的行 _score 显式还原 np.nan（借 sort_values na_position="last" 排最后）→ `a7615b6`
- **Task 4**：绘图（`analysis/plot.py` 新增 `plot_corr_matrix` 热力图 + `plot_cluster_dendrogram` 树状图，沿用 plot_sweep_heatmap / plot_factor_health_heatmap 风格）→ `1cef7b3`
- **Task 5**：`run_phase_a` 编排（state + ohlcv → 候选 → 相关矩阵 → 聚类 → 代表；output_dir 写 parquet + JSON + PNG）→ **plan-bug 修正 ×2**：① `STATE_COLS` 无 `ir` 列只有 `rolling_ir`（brief 参考 `latest[["factor","t_stat","ir"]]` 必 KeyError）→ 改从 rolling_ir 取数 rename 为 ir；② parquet round-trip 后 date 为 object(str) → `_load_state` 加 `pd.to_datetime` 规范化。另加**空候选兜底**（全部缺列被跳过时提前返回空结构）与**单因子 dendrogram 守卫**（1×1 矩阵无聚类树，跳过出图）→ `72195fa` + `4adaa8e`
- **Task 6**：`yq factor clean-a` CLI + `configs/factor_clean.yaml` + `load_factor_clean_config` → `e4e9cc4`

### 测试与提交
- 全量单测 **1091 passed**（Phase A 新增 33：correlation 19 + corr_plot 4 + factor_clean 4 + loader 3 + cli 3），ruff 干净（存量 27 处非本任务文件不碰；Task 6 的 F821×3 为 ruff 对 .yaml 的误报，检查时排除即可）
- commits：`8d5c3fd`(相关矩阵)→`bf0794d`(聚类)→`a7615b6`(代表)→`1cef7b3`(绘图)→`72195fa`(编排)→`4adaa8e`(单因子守卫)→`e4e9cc4`(CLI+配置)→`09c3a50`(clusters 形状裁定修正计划)
- 真实验证（真实 state.parquet + 全市场 ohlcv 跑 `yq factor clean-a`、核验收敛结果、PNG 落盘）由 Task 8 执行，结果在本节补记

### Task 8：全市场真实验证（2026-08-06）

- **命令**：`yq factor clean-a --state data/audit/factor_monitor_full/state.parquet --data data/clean/full_market_ohlcv.parquet --output-dir data/audit/factor_clean_a --json`（exit 0，skipped 空）
- **结果**：候选 13 个因子（2026-07-29 最新 active/decaying）→ 阈值 0.7 下 **4 簇 / 4 个代表**：
  - 簇 0 ATR 族（5 成员）：calc_atr / calc_atr_6d / calc_atr_12d / gtja_161 / gtja_175，两两相关 **0.99-1.00** → 代表 calc_atr_12d（去冗余直接证明：5 个候选收敛 1 代表）
  - 簇 1（4 成员）：calc_close_vol_rank_cov_5d / calc_vwap_vol_rank_corr_5d / gtja_99 / gtja_90，相关 **0.80** → 代表 calc_close_vol_rank_cov_5d
  - 簇 2（2 成员）：calc_high_vol_rank_corr_3d / gtja_32（与簇 1 相关 0.53-0.68）→ 代表 calc_high_vol_rank_corr_3d
  - 簇 3（2 成员）：calc_vol_rank_intraday_corr_6d / gtja_1（与簇 1 相关 0.28-0.43）→ 代表 calc_vol_rank_intraday_corr_6d
- **对照设计预期**（§4.4"4 个 GTJA 相关类收敛到 ≤2 代表"）：实际 **3 个代表**——设计文档"本质同一信号"假设过强；最近 60 日窗口下 4 类两两截面 spearman 仅 0.28-0.80，仅 close_vol_rank_cov_5d↔vwap_vol_rank_corr_5d（0.80）达 0.7 共线。monitor 的 t 值同步 ≠ 因子值共线（t 同步反映同信号族，非同向量）
- **阈值敏感性**：threshold=0.6 → high_vol_rank_corr_3d(0.68) 并入簇 1 → 3 簇；0.5 → close↔high(0.53) 并入 → 2 簇；0.4 → intraday(0.43) 并入 → 1 个量价大簇（4 个 GTJA 类收敛 1 代表）
- **产出**：`data/audit/factor_clean_a/`（corr_matrix.parquet + corr_heatmap.png + dendrogram.png + representatives.json + stderr.log）
- **阈值决策**：按计划约定不擅自调——0.7 为设计默认，事实是 4 个 GTJA 类两两相关 0.28-0.80；待用户裁决是否调整 `configs/factor_clean.yaml` 的 corr_threshold（见会话 ask 结果）
- **阈值决策（用户裁决 2026-08-06）**：**保持 corr_threshold=0.7 不变**——4 个 GTJA 类中仅 close_vol_rank_cov_5d↔vwap_vol_rank_corr_5d（0.80）达共线，high(0.53-0.68)/intraday(0.28-0.43) 是真实独立维度；去冗余的诚实结果是 **4 个代表**（ATR 族 1 + 量价族 3），组合时按 4 维度分散
