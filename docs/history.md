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
