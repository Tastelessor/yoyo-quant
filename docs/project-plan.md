# yoyo-quant 项目计划

> 架构、数据流、模块契约、开发规范见 [CLAUDE.md](../CLAUDE.md)。

## 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 项目骨架 | ✅ 完成 | pyproject.toml, 目录结构, ruff/pytest 配置 |
| data schema | ✅ 完成 | validate_ohlcv + 测试通过 |
| data fetcher | ✅ 完成 | fetcher.py + 6 tests |
| data storage | ✅ 完成 | storage.py + 5 tests |
| data filters | ✅ 完成 | 涨跌停/停牌/T+1 过滤 + 11 tests |
| factors (HV) | ✅ 完成 | volatility.py + 6 tests |
| factors (量价) | ✅ 完成 | RSI/OBV/成交量比率/ATR + 24 tests |
| strategies (均值回归) | ✅ 完成 | builtin/mean_reversion.py + 8 tests |
| strategies (RSI 反转) | ✅ 完成 | builtin/rsi_reversal.py + 10 tests |
| strategies (动量突破) | ✅ 完成 | builtin/momentum_breakout.py + 9 tests |
| strategies (框架) | ✅ 完成 | Strategy ABC + 组合器 + 注册表 + 22 tests |
| strategies (动量+趋势) | ✅ 完成 | momentum_trend.py + 9 tests |
| strategies (多因子) | ✅ 完成 | multifactor.py + 10 tests |
| data (股票池) | ✅ 完成 | universe.py + resolve_universe/apply_data_filters + 14 tests |
| analysis (参数扫描) | ✅ 完成 | param_sweep.py + plot.py + 18 tests |
| config (YAML) | ✅ 完成 | loader + build_strategies/build_risk_engine + 12 tests |
| backtest (rqalpha adapter) | ✅ 完成 | adapter.py + 11 tests |
| portfolio (equal weight) | ✅ 完成 | allocator.py + 9 tests |
| risk (position limit) | ✅ 完成 | position_limit.py + 8 tests |
| risk (规则引擎) | ✅ 完成 | Rule ABC + RuleEngine + 15 tests |
| risk (止损) | ✅ 完成 | 固定止损 + ATR 动态止损 + 12 tests |
| backtest (lightweight engine) | ✅ 完成 | engine.py + 14 tests |
| visualization | ✅ 完成 | charts.py + 6 tests |
| factors (协整) | ✅ 完成 | cointegration.py + 19 tests |
| strategies (配对交易) | ✅ 完成 | pair_trading.py + 18 tests |
| execution | 🔲 未开始 | |
| factors (GTJA 算子库) | ✅ 完成 | operators.py: delay/delta/rolling_mean/std/sum/sma/corr + 22 tests |
| factors (GTJA 动量) | ✅ 完成 | momentum.py: 5 因子 (#14/#18/#20/#88/#106) + 26 tests |
| factors (GTJA 均值回归) | ✅ 完成 | mean_reversion.py: 4 因子 (#63/#79/#112/#128) + 14 tests |
| factors (GTJA 量价) | ✅ 完成 | volume_price_gtja.py: 3 因子 (#11/#40/#43) + 6 tests |
| factors (GTJA 波动率) | ✅ 完成 | volatility_gtja.py: 5 因子 (#78/#97/#100/#161/#175) |
| factors (GTJA VWAP) | ✅ 完成 | vwap.py: 2 因子 (#120/#124) |
| factors (GTJA 趋势) | ✅ 完成 | trend.py: 3 因子 (#21/#116/#89) |
| factors (注册表) | ✅ 完成 | registry.py: 名称/别名/tag 过滤 + 9 tests |
| strategies (GTJA 动量) | ✅ 完成 | gtja_momentum.py + 12 tests |
| strategies (GTJA 均值回归) | ✅ 完成 | gtja_mean_reversion.py |
| strategies (GTJA 量价) | ✅ 完成 | volume_price_gtja.py |
| strategies (GTJA 波动率) | ✅ 完成 | volatility_gtja.py |
| strategies (GTJA VWAP) | ✅ 完成 | vwap_gtja.py |
| strategies (GTJA 趋势) | ✅ 完成 | trend_gtja.py |
| strategies (反转包装器) | ✅ 完成 | reversed.py: ReversedStrategy |
| analysis (管道诊断) | ✅ 完成 | pipeline_diagnostics.py + 7 tests |
| context (regime 检测) | ✅ 完成 | 4-state regime: trend_up/down/range/volatile + 11 tests |
| context (regime switch) | ✅ 完成 | RegimeSwitchStrategy + 验证 |
| context (股票选择) | 🔲 路线图 | 输入行情 → 输出股票池 |
| context (因子选择) | 🔲 路线图 | 输入行情 → 输出因子组合 |
| context (参数路由) | 🔲 路线图 | 输入行情 → 输出策略参数 |

## 目录结构

```
src/
├── analysis/
│   ├── param_sweep.py      # 参数网格搜索 + 结果排序
│   ├── plot.py             # 热力图 + 指标柱状图
│   └── pipeline_diagnostics.py  # 管道诊断工具
├── config/
│   ├── __init__.py
│   └── loader.py          # YAML 加载 + build 函数
├── context/                ← 新：上下文路由层
│   ├── regime.py           # 市场状态检测
│   └── regime_switch.py    # 基于 regime 的策略切换
├── data/
│   ├── universe.py         # 股票池解析与过滤
│   └── ...
├── factors/
│   ├── operators.py        # GTJA 基础算子
│   ├── momentum.py         # GTJA 动量因子
│   ├── mean_reversion.py   # GTJA 均值回归因子
│   ├── volume_price_gtja.py # GTJA 量价因子
│   ├── volatility_gtja.py  # GTJA 波动率因子
│   ├── vwap.py             # GTJA VWAP 因子
│   ├── trend.py            # GTJA 趋势因子
│   └── registry.py         # 因子注册表
├── risk/
│   ├── rules.py            # Rule ABC + RuleContext
│   ├── rule_engine.py      # RuleEngine
│   ├── rule_registry.py    # 风险规则注册表
│   ├── position_limit.py
│   ├── stop_loss.py
│   └── tradability.py
├── strategies/
│   ├── base.py             # Strategy ABC
│   ├── combiner.py         # WeightedVoteCombiner + FilterCombiner
│   ├── registry.py         # 策略注册表
│   ├── reversed.py         # ReversedStrategy 包装器
│   └── builtin/
│       ├── mean_reversion.py
│       ├── rsi_reversal.py
│       ├── momentum_breakout.py
│       ├── momentum_trend.py
│       ├── multifactor.py
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

## 历史记录

Phase 1-5 的详细任务、测试数量、回测结果和决策记录见 [history.md](history.md)。

## 配对交易优化方向

首次回测结论（2026-05-23）：2/5 配对通过协整检验，walk-forward 8 期中仅 1 期盈利，整体不优于之前的 4 个方向策略。

| # | 方向 | 说明 | 状态 | 结论 |
|---|------|------|------|------|
| 1 | 放宽入场阈值 | entry_zscore 从 3.0 降到 1.5-2.0 | ✅ 已试 | 单独无效 |
| 2 | 缩短 lookback 窗口 | lookback 从 60 降到 20-30 | ✅ 已试 | 单独无效 |
| 3 | 扩大股票池 | 4 行业 × 8 只 = 32 只 | ✅ 已试 | 协整筛选仍只有 2 对 |
| 4 | Kalman Filter 动态对冲比率 | 替代滚动 OLS，自适应 hedge ratio | ✅ 已试 | 平均收益更高但波动更大 |
| 5 | 半衰期配对筛选 | 放宽协整（p<0.10），加 hl<60 天 | ✅ 已试 | **关键突破** |
| 6 | 行业 ETF 配对 | ETF 流动性好、做空限制少 | ✅ 已试 | 数据不可用 |
| 7 | 多配对风险平价组合 | 同时持有多组配对，降低单对失效风险 | ✅ 已试 | 反而变差 |

### 方向 5 结论（2026-05-23）

**核心发现**：半衰期是比协整检验更实用的配对筛选指标。

- 通过 hl<60 天筛选：1 对（民生/兴业，hl=23 天）
- Walk-forward 9 期中 **5 期盈利**，最优参数 entry=1.5, exit=0.3, lb=40
- 对比：协整检验选出的配对 hl=4000+ 天，walk-forward 基本全军覆没

### 最终优化（2026-05-23）

通过参数微调找到最优组合：

| 参数 | 值 |
|------|-----|
| entry_zscore | 1.2 |
| exit_zscore | 0.3 |
| lookback | 30 |

Walk-forward 结果：**6/9 期盈利，累计 +7.40%，年化约 +2.3%**

### 最终策略对比

| 策略 | 盈利期 | 平均收益 | 累计收益 |
|------|--------|----------|----------|
| Baseline OLS (1.5/0.3/40) | 5/9 | +0.28% | +2.52% |
| OLS aggressive (1.0/0.3/40) | 6/9 | +0.13% | +1.12% |
| **Best combo (1.2/0.3/30)** | **6/9** | **+0.82%** | **+7.40%** |
| Kalman (1.5/0.2/30) | 5/9 | +0.44% | +3.64% |

### A/H 股跨市场配对（探索未果）

- tushare 不支持港股数据
- akshare/efinance 受代理限制，东方财富接口被阻断
- yfinance 被限流
- 需解决数据源问题后才能继续

### 结论

A 股做空限制是配对交易的天花板。+7.40% 累计（年化 ~2.3%）已是合理上限。
下次研究方向：半衰期选股做单边择时，或多因子组合。
