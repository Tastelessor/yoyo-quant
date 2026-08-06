# yoyo-quant 项目计划

> 架构、数据流、模块契约、开发规范见 [CLAUDE.md](../CLAUDE.md)。
> 详细任务记录、回测结果、决策背景见 [history.md](history.md)。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 项目骨架 | ✅ 完成 | pyproject.toml, 目录结构, ruff/pytest 配置 |
| data schema | ✅ 完成 | validate_ohlcv + 测试通过 |
| data fetcher | ✅ 完成 | fetcher.py（含 pre_close + 瞬时错误重试 + 并发 workers）+ 28 tests |
| data storage | ✅ 完成 | storage.py + 5 tests |
| data filters | ✅ 完成 | 涨跌停/停牌标注：pre_close 优先、板块幅度（创/科 20%）、停牌网格补齐 + 25 tests |
| data (清洗入口) | ✅ 完成 | clean.py: clean_market_data 一步标注三列 + 5 tests |
| data (股票池) | ✅ 完成 | universe.py + resolve_universe/apply_data_filters + 24 tests |
| data (指数成分股) | ✅ 完成 | fetcher.py: fetch_index_constituents + fetch_daily_batch + 18 tests |
| data (CSI 500 配置) | ✅ 完成 | csi500.yaml: source=index 动态获取 + 管道测试 4 tests |
| factors (HV) | ✅ 完成 | builtin/volatility.py + 6 tests |
| factors (量价) | ✅ 完成 | RSI/OBV/成交量比率/ATR + 24 tests |
| factors (协整) | ✅ 完成 | builtin/cointegration.py + 22 tests |
| factors (GTJA 算子库) | ✅ 完成 | operators.py: 11 算子 (delay/delta/rolling_mean/std/sum/sma/corr/rank/ts_max/ts_min/rolling_cov) + 39 tests |
| factors (GTJA 动量) | ✅ 完成 | builtin/momentum.py: 5 因子 (#14/#18/#20/#88/#106) + 26 tests |
| factors (GTJA 均值回归) | ✅ 完成 | builtin/mean_reversion.py: 4 因子 (#63/#79/#112/#128) + 14 tests |
| factors (GTJA 量价) | ✅ 完成 | builtin/volume_price_gtja.py: 18 因子 + 36 tests |
| factors (GTJA 波动率) | ✅ 完成 | builtin/volatility_gtja.py: 5 因子 (#78/#97/#100/#161/#175) |
| factors (GTJA VWAP) | ✅ 完成 | builtin/vwap.py: 2 因子 (#120/#124) |
| factors (GTJA 趋势) | ✅ 完成 | builtin/trend.py: 3 因子 (#21/#116/#89) |
| factors (注册表) | ✅ 完成 | registry.py: 93 条目（51 single + 5 pair + 37 别名）, 名称/别名/tag/kind 过滤 + run_factor 缓存 + 41 tests |
| factors (结果缓存) | ✅ 完成 | ops/cache.py: 磁盘 parquet 缓存，键=(因子名, 参数哈希, 数据指纹) + 7 tests |
| factors (因子评估) | ✅ 完成 | ops/evaluation.py: IC/IR + forward return + 分层回测 + 批量比较表 + 30 tests |
| CLI (yq) | ✅ 完成 | yq 包: factor list(含 --verbose 因子介绍)/run/evaluate + cache info/clear，typer 实现，文本/--json 双输出，python -m + console script 双入口，notebooks/icir_factor_screening.py 一键筛查 + 39 tests |
| strategies (均值回归) | ✅ 完成 | builtin/mean_reversion.py + 8 tests |
| strategies (RSI 反转) | ✅ 完成 | builtin/rsi_reversal.py + 10 tests |
| strategies (动量突破) | ✅ 完成 | builtin/momentum_breakout.py + 9 tests |
| strategies (动量+趋势) | ✅ 完成 | builtin/momentum_trend.py + 9 tests |
| strategies (多因子) | ✅ 完成 | builtin/multifactor.py + 10 tests |
| strategies (配对交易) | ✅ 完成 | builtin/pair_trading.py + 19 tests |
| strategies (框架) | ✅ 完成 | Strategy ABC + 组合器 + 注册表 + 22 tests |
| strategies (GTJA 动量) | ✅ 完成 | builtin/gtja_momentum.py + 12 tests |
| strategies (GTJA 均值回归) | ✅ 完成 | builtin/gtja_mean_reversion.py |
| strategies (GTJA 量价) | ✅ 完成 | builtin/volume_price_gtja.py |
| strategies (GTJA 波动率) | ✅ 完成 | builtin/volatility_gtja.py |
| strategies (GTJA VWAP) | ✅ 完成 | builtin/vwap_gtja.py |
| strategies (GTJA 趋势) | ✅ 完成 | builtin/trend_gtja.py |
| strategies (反转包装器) | ✅ 完成 | reversed.py: ReversedStrategy |
| strategies (市场状态) | ✅ 完成 | builtin/market_regime.py: MA 交叉仓位暴露 + 15 tests |
| portfolio (equal weight) | ✅ 完成 | allocator.py + 9 tests |
| portfolio (circuit breaker) | ✅ 完成 | DrawdownCircuitBreaker: 回撤触发仓位压缩 + dead-zone + fast recovery + 22 tests |
| backtest (slippage 修复) | ✅ 完成 | _apply_slippage 忽略 boolean limit_up/down，防止 min(price,False)=0 |
| risk (position limit) | ✅ 完成 | position_limit.py + 14 tests |
| risk (规则引擎) | ✅ 完成 | Rule ABC + RuleEngine + 15 tests |
| risk (止损) | ✅ 重构 | 止损逻辑已迁移到 BacktestEngine，Risk 层仅保留截面过滤规则 |
| backtest (rqalpha adapter) | ✅ 完成 | adapter.py + 11 tests |
| backtest (lightweight engine) | ✅ 完成 | engine.py: SL/TP/ATR + TradingCost(佣金/印花税/过户费/滑点) + 39 tests |
| backtest (walk-forward) | ✅ 完成 | walk_forward.py: 资金链式传递 + compute_overall_metrics + 22 tests |
| backtest (连续回测) | ✅ 完成 | continuous.py: 单次通过无 train/test 切分 + 9 tests |
| backtest (统一管道) | ✅ 完成 | pipeline.py: build_positions/run_backtest/run_pipeline 收敛 walk_forward/continuous/param_sweep/pool_matrix 4 处重复管道 + 17 tests |
| visualization | ✅ 完成 | charts.py + 9 tests |
| analysis (参数扫描) | ✅ 完成 | param_sweep.py + plot.py + 18 tests |
| analysis (管道诊断) | ✅ 完成 | pipeline_diagnostics.py + 7 tests |
| analysis (行业矩阵) | ✅ 完成 | pool_matrix.py: 策略×行业交叉回测 + 12 tests |
| analysis (因子生命周期监控) | ✅ 完成 | factor_monitor.py: 滚动 IC/IR/t 状态机（active/decaying/dead/reverse）+ 尾部增量 + 持久化 + 绘图 + yq factor monitor CLI；evaluation.py +3 滚动原语 + 47 tests |
| config (YAML) | ✅ 完成 | loader + build_strategies/build_risk_engine/build_regime_switch + 12 tests |
| context (regime 检测) | ✅ 完成 | breadth + 自适应波动率 + EMA + 持续期 + 指数过滤 + 19 tests |
| context (regime switch) | ✅ 完成 | RegimeSwitchStrategy + confirmation_lag(10) + build_regime_switch |
| factors (行业中性化) | ✅ 完成 | ops/neutralize.py: 截面去均值 + min_peers 动态降级 + 18 tests |
| portfolio (持仓平滑) | ✅ 完成 | smoother.py: 宽表状态机逐日递推 + 死区拦截 + 14 tests |
| strategies (twin-star combiner) | ✅ 完成 | threshold=0.5 AND-gate 共识过滤 + 中性化 → Sharpe 0.820 |
| context (股票选择器) | ✅ 完成 | stock_selector.py: 因子质量评估 + 动态股票池筛选 + 40 tests |
| data (盈利断层) | ✅ 完成 | earnings.py: PIT 滚动池 + Z-Score 标准化 + 27 tests |
| factors (盈利断层) | ✅ 完成 | builtin/earnings.py: calc_earnings_surprise + calc_earnings_acceleration + 7 tests |
| strategies (盈利断层) | ✅ 完成 | earnings_surprise.py: GTJAEarningsSurpriseStrategy + 12 tests |
| factors (价值) | ✅ 完成 | builtin/value.py: calc_ep(EP=1/PE) + calc_bp(BP=1/PB) + 17 tests |
| factors (流动性) | ✅ 完成 | builtin/liquidity.py: calc_amihud + calc_turnover + 13 tests |
| data (季度财务) | ✅ 完成 | fundamentals_quarterly.py: fina_indicator PIT 面板 + 7 tests |
| data (交易日历) | ✅ 完成 | trade_calendar.py: 权威交易日历（tushare trade_cal + parquet 缓存）+ 19 tests |
| factors (质量) | ✅ 完成 | builtin/quality.py: roe_level + roe_stability + cashflow_quality + 10 tests |
| factors (分层) | ✅ 完成 | Phase 0: builtin/(13 因子实现) + ops/(评估/中性化/缓存) 分层；顶层 re-export 兼容 + 1058 单测 + 30 pipeline |
| factors (相关性去冗余) | ✅ 完成 | Phase A: ops/correlation.py（相关矩阵+聚类+代表）+ analysis/factor_clean.py 编排 + yq factor clean-a + factor_clean.yaml |
| factors (walk-forward OOS) | ✅ 完成 | Phase B: ops/oos.py（窗口生成+选因子+test 统计+bootstrap 零分布）+ analysis/factor_oos.py 编排 + yq factor clean-b + factor_clean.yaml Phase B 段 |
| strategies (基本面组合) | ✅ 完成 | fundamental_diversified.py: 3 因子 IR 加权（评估后从 9 个候选中筛选）+ YAML 配置 |
| context (因子选择) | 🔲 路线图 | 输入行情 → 输出因子组合 |
| context (参数路由) | ✅ 完成 | param_router.py: per-regime rebalance/top_n 路由 + 10 tests |
| strategies (多类别组合) | ✅ 完成 | multi_category.py: 6 类别加权投票 + 7 tests |
| data (指数成分股) | ✅ 完成 | fetcher.py: fetch_index_constituents + fetch_daily_batch + 18 tests |
| data (全市场基本筛选) | ✅ 完成 | fetcher.py: fetch_all_stocks + fetch_fundamentals + apply_fundamental_filters |
| risk (止盈规则) | ✅ 重构 | 已迁移到 BacktestEngine（与止损统一管理） |
| execution | 🔲 未开始 | 统一下单接口 |

**测试总计**：916 tests（单元 890 + 管道 26，63 个测试文件；集成测试因 TUSHARE_TOKEN 过期跳过/失败，见 history.md）

## 目录结构

```
src/
├── analysis/
│   ├── param_sweep.py           # 参数网格搜索 + 结果排序
│   ├── plot.py                  # 热力图 + 指标柱状图 + 因子生命周期双轴图/健康热力图 + OOS 胜率图/bootstrap 零分布对比图
│   ├── pipeline_diagnostics.py  # 管道诊断工具
│   ├── pool_matrix.py           # 策略 × 行业矩阵回测
│   ├── factor_monitor.py        # 因子生命周期状态机 + 尾部增量 + 持久化
│   └── factor_oos.py            # Phase B: walk-forward OOS 编排（train 选 → test 验）
├── config/
│   ├── __init__.py
│   └── loader.py                # YAML 加载 + build 函数
├── context/                     # 上下文路由层
│   ├── regime.py                # 市场状态检测
│   ├── regime_switch.py         # 基于 regime 的策略切换
│   └── stock_selector.py        # 因子质量评估 + 动态股票池
├── data/
│   ├── universe.py              # 股票池解析与过滤
│   └── ...
├── factors/
│   ├── __init__.py              # 顶层 re-export（from factors import X 兼容）
│   ├── registry.py              # 因子注册表 (93 条目: 88 single + 5 pair) + run_factor/calc_factors
│   ├── operators.py             # GTJA 基础算子 (11 个)
│   ├── builtin/                 # 因子实现 (13 个，只依赖 operators + pandas)
│   │   ├── momentum.py          # GTJA 动量因子 (5)
│   │   ├── mean_reversion.py    # GTJA 均值回归因子 (4)
│   │   ├── volume_price_gtja.py # GTJA 量价/情绪/资金流因子 (18)
│   │   ├── volatility_gtja.py   # GTJA 波动率因子 (5)
│   │   ├── vwap.py              # GTJA VWAP 因子 (2)
│   │   ├── trend.py             # GTJA 趋势因子 (3)
│   │   ├── volume_price.py      # 通用量价因子 (RSI/OBV/ATR/VR)
│   │   ├── volatility.py        # HV 因子
│   │   ├── cointegration.py     # 协整/半衰期/Kalman Filter (pair 专用)
│   │   ├── earnings.py          # 盈利断层因子
│   │   ├── value.py             # 价值因子 (EP/BP)
│   │   ├── quality.py           # 质量因子 (ROE/现金流)
│   │   └── liquidity.py         # 流动性因子 (Amihud/换手)
│   └── ops/                     # 对因子的操作（评估/中性化/缓存 + 后续清洗）
│       ├── evaluation.py        # 因子评估 (IC/IR/forward return/分层/滚动统计)
│       ├── neutralize.py        # 行业中性化
│       ├── cache.py             # 因子结果磁盘缓存 (parquet, 键含参数哈希+数据指纹)
│       ├── correlation.py       # Phase A: 截面相关矩阵 + 聚类去冗余
│       └── oos.py               # Phase B: walk-forward 窗口生成/选因子/test 统计/零分布
├── yq/                          # 命令行工具 (typer)
│   ├── cli.py                   # 根入口: factor/cache 子命令组 + --version
│   ├── factors.py               # yq factor list/run/evaluate
│   ├── cache.py                 # yq cache info/clear
│   ├── output.py                # 文本表格 / --json 渲染层 (NaN→null)
│   └── __main__.py              # python -m yq 入口
├── risk/
│   ├── rules.py                 # Rule ABC + RuleContext
│   ├── rule_engine.py           # RuleEngine
│   ├── rule_registry.py         # 风险规则注册表
│   ├── position_limit.py
│   └── tradability.py
├── strategies/
│   ├── base.py                  # Strategy ABC
│   ├── combiner.py              # WeightedVoteCombiner + FilterCombiner
│   ├── builtin/
│   │   ├── multi_category.py    # 多类别因子组合策略
│   ├── registry.py              # 策略注册表 (13 策略)
│   ├── reversed.py              # ReversedStrategy 包装器
│   └── builtin/
│       ├── mean_reversion.py
│       ├── rsi_reversal.py
│       ├── momentum_breakout.py
│       ├── momentum_trend.py
│       ├── multifactor.py
│       ├── pair_trading.py
│       ├── market_regime.py     # MA 交叉仓位暴露
│       ├── gtja_momentum.py
│       ├── gtja_mean_reversion.py
│       ├── volume_price_gtja.py
│       ├── volatility_gtja.py
│       ├── vwap_gtja.py
│       └── trend_gtja.py
├── backtest/
│   ├── pipeline.py               # 统一管道编排（build_positions/run_backtest/run_pipeline）
├── portfolio/
│   ├── allocator.py               # equal_weight + exposure scaling
│   ├── circuit_breaker.py         # DrawdownCircuitBreaker: 回撤断路器
│   ├── smoother.py                # 持仓平滑死区状态机
│   ├── industry_cap.py            # 行业上限约束
│   └── industry_momentum.py       # 行业动量
├── visualization/
└── execution/
configs/
├── default.yaml               # CSI 300 默认配置
├── production.yaml            # Phase 14 生产配置（twin-star + 中性化 + threshold=0.5）
├── csi500.yaml                # CSI 500 中盘配置
└── full_market.yaml           # 全市场基本筛选配置
```

## Context 层路线图

核心理念：**特定行情 + 特定股票 + 特定参数 + 特定策略因子 = 长期有效**

| # | 组件 | 状态 | 说明 |
|---|------|------|------|
| 1 | Regime 检测 | ✅ | breadth + 自适应波动率 + EMA + 持续期 + 指数过滤，4 种 regime |
| 2 | Regime Switch | ✅ | confirmation_lag=10 + 按 regime 切换子策略 |
| 3 | 股票选择器 | ✅ | factor_coverage + rank_stability + factor_dispersion → 日频动态选股 |
| 4 | 参数路由 | ✅ | route_params(regime) → {rebalance, top_n, bottom_n} |
| 5 | 因子选择 | ✅ | 实证结论：per-regime 因子权重切换增量极小，regime 价值在避险不在择因子 |

### Context 层实证总结（2026-05-26）

| 验证项 | 结论 | 证据 |
|--------|------|------|
| 因子审计 × regime | 因子稳定性排名跨 regime 高度一致，per-regime 切换无增量 | spread < 0.15 for most factors |
| 参数路由 | 存量参数差异化不足以产生正向信号 | ΔSharpe=-0.077 vs fixed |
| 因子选择 | 不同 regime 下最优因子类别差异小，volatility 在 trend_up 略有优势 | 6×4 regime×category 矩阵 |
| Regime 避险 | 空仓坏行情 + lag=10 → MaxDD -3.5%, Sharpe +0.10 | 首次全方位优于全 regime 交易 |
| 确认期 | lag=10 是 sweet spot，lag=7 太短 | 46→32 flips |

**核心发现**：Context 层的优化空间已经不大。regime detection 的精度瓶颈在信号层，不在路由层。更大的 alpha 增量在多类别因子组合（信号层）和行业感知分配（组合层）。

## 下一阶段路线图

### 现状诊断（Phase 14 结项，2026-05-28）

> **注意（2026-05-29 修正）**：以下数字基于旧的 per-period 平均算法，Sharpe 和年化收益被高估。
> 新的 `compute_overall_metrics` 从连续权益曲线计算正确指标。旧数字保留作相对比较参考，
> 绝对值需重跑 notebook 确认。

生产配置（twin-star + 中性化 + threshold=0.5 + dead_zone=0.01）10 年全周期回测：
- **旧算法：Sharpe 0.820 (per-period mean), 年化 24% (per-period mean), MaxDD 7.8%, Cumulative 312%, Trades 920**

瓶颈在**特异性风险暴露**：组合仅持有 ~2 只股票（50% 权重），个股极端回撤直接传导至 NAV，跨期 Sharpe 标准差 1.869。

| 限速因素 | 证据 |
|---------|------|
| 信号源同构 | 双子星均为微观行情项因子，相关性 0.467，共享流动性风险暴露 |
| 持仓过度集中 | ~2 只股票，退化为"高确信度个股博弈"，大数定律失效 |
| 跨期不稳定 | 最好 +129%，最差 -53%，机构审计无法通过 |

### 可行路径（优先级排序）

| # | 方向 | 层级 | 状态 | 说明 |
|---|------|------|------|------|
| A | ~~多类别因子组合~~ | 信号层 | **已验证** | Sharpe 0.487 vs 单策略 0.606。弱策略稀释 alpha，但降低 MaxDD |
| B | ~~行业感知分配~~ | 组合层 | **已验证无效** | 行业 cap 无增量。90 个行业已分散，cap 只限制自由度不降风险 |
| C | **CSI 500 + earnings** | 数据层 | **✅ Phase 16 验证** | 量价策略在 CSI 500 无效，但 earnings_surprise 在 CSI 500 Sharpe 0.930（walk-forward）/ 0.333（连续），是目前最优组合 |
| E | ~~全市场 + stock_selector~~ | 数据层 | **已验证无效** | stock_selector 质量过滤无正向价值。可投池（市值>200亿，844只）Sharpe 0.43 已是最优 |
| F | **小止盈大止损** | 风控层 | **已实现但不适用** | SL/TP 对均值回归有害（割肉+截断利润），适合趋势策略 |
| G | ~~DrawdownCircuitBreaker~~ | 风控层 | **已验证** | MaxDD 降 5.6pp（-33.4%→-27.8%），但 Sharpe 降 0.076。阈值锁 -0.35 作安全底线 |
| H | **基本面盈利断层因子** | 信号层 | **✅ Phase 15 完成** | earnings-only N=10 rb=15: 旧算法 Sharpe 0.989 (per-period mean), MaxDD 7.3%, Return 363% (compound)。纯基本面 > 混合组合。需重跑确认绝对值 |
| D | Execution 模块 | 基础层 | 待做 | 统一下单接口 |

### Direction C 验证结果（2026-05-27）

CSI 300 vs CSI 500 回测（2023-01 ~ 2026-05，5 策略）：

| Strategy | CSI300 Sharpe | CSI500 Sharpe | Delta |
|----------|---------------|---------------|-------|
| reversed_gtja_vwap | 0.606 | 0.106 | **-0.500** |
| gtja_momentum | 0.485 | 0.246 | **-0.239** |
| gtja_volatility | 0.427 | 0.047 | **-0.380** |
| gtja_volume_price | 0.352 | 0.369 | +0.017 |
| gtja_vwap | 0.336 | 0.382 | +0.046 |
| **平均** | **0.441** | **0.230** | **-0.211** |

结论：CSI 300 全面碾压 CSI 500。中盘股噪声更大、趋势持续性差、流动性低（CSI 500 均量仅为 CSI 300 的 48%）。2023-2026 是大盘股驱动的行情，中盘扩展不提供 alpha 增量。

### Direction E 验证结果（2026-05-27）

全市场 + stock_selector 实验（2023-01 ~ 2026-05，gtja_momentum 策略，walk-forward 12m/3m）：

| 配置 | 股票池 | Sharpe | Return | MaxDD |
|------|--------|--------|--------|-------|
| CSI 300 baseline | 100 只 | 0.20 | +4.0% | 13.0% |
| 可投池（市值>200亿）| 844 只 | **0.43** | +4.4% | 13.3% |
| 可投池 + selector min_pass=1 | 301 只 | 0.29 | +1.8% | 18.5% |
| 可投池 + selector min_pass=3 + top50 | 54 只 | 0.24 | -69.4% | 83.3% |

结论：stock_selector 的数据质量过滤没有正向价值，反而损害收益。数据质量好 ≠ alpha 好。真正有效的是可投池硬约束（市值>200亿）。

### 执行建议

### Direction B 验证结果（2026-05-27）

行业 cap 约束实验（2023-01 ~ 2026-05，gtja_momentum，可投池 844 只）：

| 配置 | 总收益 | Sharpe | MaxDD | 交易数 |
|------|--------|--------|-------|--------|
| No cap (baseline) | +4.4% | 0.43 | 13.3% | 40 |
| Cap 30% | +3.7% | 0.38 | 13.2% | 40 |
| Cap 20% | +2.8% | 0.33 | 12.9% | 40 |

结论：行业 cap 没有帮助。当前组合本身行业分布已经分散（90 个行业），不存在单行业过度集中。加 cap 只限制了策略自由度，没有降低实际风险。

### 多策略组合实验（2026-05-27）

回撤归因显示：真实 MaxDD 47.9%（非 walk-forward 的 13.3%），主因是科技行业集中 + 个股集中，2023-2024 动量策略系统性失效。

策略相关性矩阵：

| 策略 | momentum | rev_vwap | vol_price | volatility | mean_rev |
|------|----------|----------|-----------|------------|----------|
| momentum | 1.00 | 0.37 | 0.58 | 0.66 | 0.22 |
| reversed_gtja_vwap | 0.37 | 1.00 | 0.28 | 0.26 | 0.28 |

50/50 组合网格搜索结果：

| 配置 | Sharpe | Return | MaxDD | Calmar |
|------|--------|--------|-------|--------|
| momentum 单独 | 0.48 | 206.2% | -35.9% | 5.74 |
| 50/50 mom+rev_vwap | **0.63** | 187.3% | **-22.9%** | **8.17** |
| 60/40 | 0.64 | 191.1% | -25.2% | 7.59 |
| 70/30 | 0.64 | 194.9% | -27.6% | 7.05 |

**定版配置：gtja_momentum 50% + reversed_gtja_vwap 50%**

极端场景验证：
- 2024 Q1 流动性危机：MaxDD -6.1%
- 最长连续 17 次亏损：MaxDD 未恶化
- 止损 -10%：几乎无影响（Sharpe 0.50→0.51）
- 最差单日 -16.57%：7 天后反弹 +21.64%

样本外验证：
- Train ≤2020 → Test 2021+: Sharpe 0.34, MaxDD -22.9%
- Train ≤2022 → Test 2023+: Sharpe 0.46, MaxDD -20.8%
- Train ≤2023 → Test 2024+: Sharpe 0.89, MaxDD -10.2%

**下一步：Execution 模块（统一下单接口）**

## 策略矩阵（10 年窗口，2016-2026）

| 策略 | 类型 | 最佳行业 | 备注 |
|------|------|---------|------|
| gtja_momentum | 动量 | 科技(0.61), 装备制造(0.40) | 唯一跨周期稳定策略 |
| reversed_gtja_vwap | 均值回归 | 能源(0.47) | 3 年强但 10 年弱 |
| gtja_volatility | 波动率 | 通信(0.46), 电子(0.50) | MaxDD 偏高(60%+) |
| gtja_vwap | 综合 | 消费(0.49), 新能源(0.42) | 大盘防御型 |
| gtja_volume_price | 量价 | 银行(0.22), 医药(0.08) | 防御型行业专属 |

详细回测数据和决策记录见 [history.md](history.md)。
