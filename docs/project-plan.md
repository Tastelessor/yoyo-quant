# yoyo-quant 项目计划

> 架构、数据流、模块契约、开发规范见 [CLAUDE.md](../CLAUDE.md)。
> 详细任务记录、回测结果、决策背景见 [history.md](history.md)。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 项目骨架 | ✅ 完成 | pyproject.toml, 目录结构, ruff/pytest 配置 |
| data schema | ✅ 完成 | validate_ohlcv + 测试通过 |
| data fetcher | ✅ 完成 | fetcher.py + 7 tests |
| data storage | ✅ 完成 | storage.py + 5 tests |
| data filters | ✅ 完成 | 涨跌停/停牌/T+1 过滤 + 5 tests |
| data (股票池) | ✅ 完成 | universe.py + resolve_universe/apply_data_filters + 24 tests |
| data (指数成分股) | ✅ 完成 | fetcher.py: fetch_index_constituents + fetch_daily_batch + 18 tests |
| data (CSI 500 配置) | ✅ 完成 | csi500.yaml: source=index 动态获取 + 管道测试 4 tests |
| factors (HV) | ✅ 完成 | volatility.py + 6 tests |
| factors (量价) | ✅ 完成 | RSI/OBV/成交量比率/ATR + 24 tests |
| factors (协整) | ✅ 完成 | cointegration.py + 22 tests |
| factors (GTJA 算子库) | ✅ 完成 | operators.py: 11 算子 (delay/delta/rolling_mean/std/sum/sma/corr/rank/ts_max/ts_min/rolling_cov) + 39 tests |
| factors (GTJA 动量) | ✅ 完成 | momentum.py: 5 因子 (#14/#18/#20/#88/#106) + 26 tests |
| factors (GTJA 均值回归) | ✅ 完成 | mean_reversion.py: 4 因子 (#63/#79/#112/#128) + 14 tests |
| factors (GTJA 量价) | ✅ 完成 | volume_price_gtja.py: 18 因子 + 36 tests |
| factors (GTJA 波动率) | ✅ 完成 | volatility_gtja.py: 5 因子 (#78/#97/#100/#161/#175) |
| factors (GTJA VWAP) | ✅ 完成 | vwap.py: 2 因子 (#120/#124) |
| factors (GTJA 趋势) | ✅ 完成 | trend.py: 3 因子 (#21/#116/#89) |
| factors (注册表) | ✅ 完成 | registry.py: 46 因子, 名称/别名/tag 过滤 + 9 tests |
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
| risk (position limit) | ✅ 完成 | position_limit.py + 14 tests |
| risk (规则引擎) | ✅ 完成 | Rule ABC + RuleEngine + 15 tests |
| risk (止损) | ✅ 完成 | 固定止损 + ATR 动态止损 + 12 tests |
| backtest (rqalpha adapter) | ✅ 完成 | adapter.py + 11 tests |
| backtest (lightweight engine) | ✅ 完成 | engine.py + 15 tests |
| backtest (walk-forward) | ✅ 完成 | walk_forward.py + 11 tests |
| visualization | ✅ 完成 | charts.py + 9 tests |
| analysis (参数扫描) | ✅ 完成 | param_sweep.py + plot.py + 18 tests |
| analysis (管道诊断) | ✅ 完成 | pipeline_diagnostics.py + 7 tests |
| analysis (行业矩阵) | ✅ 完成 | pool_matrix.py: 策略×行业交叉回测 + 12 tests |
| config (YAML) | ✅ 完成 | loader + build_strategies/build_risk_engine/build_regime_switch + 12 tests |
| context (regime 检测) | ✅ 完成 | breadth + 自适应波动率 + EMA + 持续期 + 指数过滤 + 19 tests |
| context (regime switch) | ✅ 完成 | RegimeSwitchStrategy + confirmation_lag(10) + build_regime_switch |
| context (股票选择器) | ✅ 完成 | stock_selector.py: 因子质量评估 + 动态股票池筛选 + 40 tests |
| context (因子选择) | 🔲 路线图 | 输入行情 → 输出因子组合 |
| context (参数路由) | ✅ 完成 | param_router.py: per-regime rebalance/top_n 路由 + 10 tests |
| execution | 🔲 未开始 | 统一下单接口 |

**测试总计**：597 tests（43 个测试文件）

## 目录结构

```
src/
├── analysis/
│   ├── param_sweep.py           # 参数网格搜索 + 结果排序
│   ├── plot.py                  # 热力图 + 指标柱状图
│   ├── pipeline_diagnostics.py  # 管道诊断工具
│   └── pool_matrix.py           # 策略 × 行业矩阵回测
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
│   ├── operators.py             # GTJA 基础算子 (11 个)
│   ├── momentum.py              # GTJA 动量因子 (5)
│   ├── mean_reversion.py        # GTJA 均值回归因子 (4)
│   ├── volume_price_gtja.py     # GTJA 量价/情绪/资金流因子 (18)
│   ├── volatility_gtja.py       # GTJA 波动率因子 (5)
│   ├── vwap.py                  # GTJA VWAP 因子 (2)
│   ├── trend.py                 # GTJA 趋势因子 (3)
│   ├── volume_price.py          # 通用量价因子 (RSI/OBV/ATR/VR)
│   ├── volatility.py            # HV 因子
│   ├── cointegration.py         # 协整/半衰期/Kalman Filter
│   └── registry.py              # 因子注册表 (46 因子)
├── risk/
│   ├── rules.py                 # Rule ABC + RuleContext
│   ├── rule_engine.py           # RuleEngine
│   ├── rule_registry.py         # 风险规则注册表
│   ├── position_limit.py
│   ├── stop_loss.py
│   └── tradability.py
├── strategies/
│   ├── base.py                  # Strategy ABC
│   ├── combiner.py              # WeightedVoteCombiner + FilterCombiner
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
├── portfolio/
├── visualization/
└── execution/
configs/
└── default.yaml
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

### 现状诊断

当前 full-period 回测天花板：Sharpe 0.56, 年化 12.6%, MaxDD 22.5%（mean_reversion 单类别）。
加 regime 避险后：Sharpe 0.66, 年化 10.8%, MaxDD 19.1%。Calmar 0.57——不算好。

瓶颈不在 context 层，在**信号层**。因子质量决定了信息比率上限，context 只能在这个上限内做风险预算。

| 限速因素 | 证据 |
|---------|------|
| A 股大市值 alpha 天花板 | 10y 行业矩阵最好 Sharpe 0.61 |
| 单因子类别极限 | mean_reversion 最好 0.56，其余 < 0.52 |
| 长多限制 | 24% 天数（trend_down+volatile）无法获利，只能空仓 |
| 股票池有效性 | CSI 300 大市值定价效率高，alpha 天然受限 |

### 可行路径（优先级排序）

| # | 方向 | 层级 | 预期增量 | 说明 |
|---|------|------|---------|------|
| A | **多类别因子组合** | 信号层 | 大 | 6 个类别加权组合（momentum+mean_rev+vol_price+volatility+vwap+trend），而非只用 mean_reversion。多个低相关 alpha 源叠加可把 Sharpe 从 0.56 推到 0.7+ |
| B | **行业感知分配** | 组合层 | 中 | 不同行业最优策略不同（科技 momentum Sharpe 0.61 vs 消费 VWAP 0.49）。行业×策略路由的分化 > regime×策略路由 |
| ~~C~~ | ~~扩大股票池到中盘~~ | ~~数据层~~ | ~~中~~ | **已验证无效**。CSI 500 平均 Sharpe 0.23 vs CSI 300 的 0.44，所有策略在中盘股上表现更差（详见下方） |
| D | Execution 模块 | 基础层 | — | 统一下单接口。不做能赚钱，但管道不完整 |

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

### 执行建议

**先 A → 验证 → 再 B**（C 已排除）

A 是最大的增量来源，且改动最小（用一个 MultiCategoryStrategy 包装 6 个类别，weighted vote 输出信号）。验证后如果 Sharpe 过 0.7，再做 B 进一步优化分配。
- **Coverage**：因子值是否可计算？
- **Rank Stability**：排名是否跨期稳定（rank autocorrelation）？
- **Dispersion**：因子是否区分股票（cross-sectional CV）？

## 策略矩阵（10 年窗口，2016-2026）

| 策略 | 类型 | 最佳行业 | 备注 |
|------|------|---------|------|
| gtja_momentum | 动量 | 科技(0.61), 装备制造(0.40) | 唯一跨周期稳定策略 |
| reversed_gtja_vwap | 均值回归 | 能源(0.47) | 3 年强但 10 年弱 |
| gtja_volatility | 波动率 | 通信(0.46), 电子(0.50) | MaxDD 偏高(60%+) |
| gtja_vwap | 综合 | 消费(0.49), 新能源(0.42) | 大盘防御型 |
| gtja_volume_price | 量价 | 银行(0.22), 医药(0.08) | 防御型行业专属 |

详细回测数据和决策记录见 [history.md](history.md)。
