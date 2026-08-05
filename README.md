# yoyo-quant

A 股量化策略研究框架 —— 从数据到回测的完整管道，专注系统性策略验证而非"看指标猜涨跌"。

## 当前能力

- **100 只 CSI 300 大市值股票**，覆盖 11 个行业板块
- **93 个因子注册条目**（51 single + 5 pair + 37 别名，覆盖动量/均值回归/量价/波动率/VWAP/趋势），11 个可复用算子，注册表支持名称/别名/tag/kind 过滤 + 磁盘缓存
- **13 个策略**：6 个 GTJA 因子策略 + 均值回归/RSI 反转/动量突破/动量趋势/多因子/配对交易/市场状态
- **策略包装器**：ReversedStrategy（反向信号）、RegimeSwitchStrategy（市场状态自适应路由）
- **Context 路由层**：regime 检测 → 策略切换 → 参数路由（rebalance/top_n per regime），股票选择器（因子质量评估 → 动态股票池）
- **完整回测管道**：data → factors → strategies → portfolio → risk → backtest → visualization
- **风控引擎**：可组合规则引擎（止损/仓位限制/T+1/涨跌停过滤）+ DrawdownCircuitBreaker（回撤断路器）
- **交易摩擦模型**：佣金（万1/最低5元）+ 印花税（万5/卖出单边）+ 过户费 + 滑点 tick + 涨跌停价格剪裁
- **分析工具**：参数网格扫描、管道诊断、策略×行业矩阵、因子审计（全局 + per-regime）
- **因子评估**：IC/IR、前向收益、分层回测（`evaluation.py`）
- **命令行工具 `yq`**：因子注册表查询 / 计算 / IC-IR 评估 / 缓存管理（`python -m yq` 或安装后 `yq`）
- **1007 个测试**：单元测试 + 管道测试 + 集成测试

## 定版配置回测结果

50% gtja_momentum + 50% reversed_gtja_vwap，100 只 CSI 300，2016-05 ~ 2026-05 全周期连续回测：

| 指标 | 值 |
|------|-----|
| 总收益 | 211.9% |
| 年化收益 | 12.54% |
| Sharpe | 0.611 |
| 最大回撤 | -33.4% |
| 交易次数 | 5806 |

## 数据流

回测管道（7 步，单向）：

```
configs/default.yaml
  │ load_config()
  ▼
[1] src/config/loader.py
    build_strategies() / build_risk_engine() / build_regime_switch()
    └── 产出：策略实例 + 风控引擎实例
  │
  ▼
[2] src/data/
    fetcher.py         fetch_daily(code, start, end)    ──┐
    storage.py         load_parquet() / save_parquet()   ──┤ 行情获取与缓存
    filters.py         detect_limit_price()              ──┤ 涨跌停/停牌标注
                        detect_suspension()              ──┤
    universe.py        resolve_universe()                ──┘ 股票池解析
    └── 产出：OHLCV DataFrame（含 limit_up/limit_down/is_suspended 列）
  │
  ▼
[3] src/factors/
    operators.py       11 个算子 (delay/rank/corr/sma/ts_max/...)
    registry.py        因子注册表 (46 因子, 名称/别名/tag 过滤)
    momentum.py        5   (#14 #18 #20 #88 #106)
    mean_reversion.py  4   (#63 #79 #112 #128)
    volume_price_gtja  18  (#1 #11 #12 #29 #32 #40 #43 #47 #54 #70
    .py                     #80 #90 #99 #102 #118 #139 #145 #178)
    volatility_gtja.py 5   (#78 #97 #100 #161 #175)
    vwap.py            2   (#120 #124)
    trend.py           3   (#21 #89 #116)
    volatility.py      1   (HV)
    volume_price.py    4   (RSI OBV ATR volume_ratio)
    cointegration.py   4   (spread zscore half_life kalman)
    └── 产出：因子 DataFrame（date + code + 因子列）
  │
  ▼
[4] src/context/ + src/strategies/ + src/portfolio/
    ┌─ context 层（市场感知，先于策略执行）─────────────────────┐
    │ regime.py          detect_regime() → trend_up/down/range/volatile   │
    │ regime_switch.py   RegimeSwitchStrategy → 按 regime 选择子策略       │
    │ param_router.py    route_params(regime) → {rebalance, top_n, ...}   │
    │ stock_selector.py  select_tradable() → 按因子质量筛选股票池           │
    └────────────────────────────────────────────────────────────────────┘
    ┌─ strategies 层（信号生成）─────────────────────────────────┐
    │ base.py            Strategy ABC                                     │
    │ registry.py        register_strategy / get_strategy (13 策略)       │
    │ combiner.py        WeightedVoteCombiner / FilterCombiner             │
    │ reversed.py        ReversedStrategy（信号翻转包装器）                │
    │ builtin/           13 个策略实现                                    │
    └────────────────────────────────────────────────────────────────────┘
    ┌─ portfolio 层（仓位分配 + 风控叠加）───────────────────────┐
    │ allocator.py       equal_weight(signals, prices, capital, exposure) │
    │ circuit_breaker.py DrawdownCircuitBreaker                           │
    │   └── 阈值触发 → 渐进压缩 exposure → fast recovery 动量解除         │
    │   └── dead-zone: 仅当 exposure 变化 > 5% 时才调整持仓               │
    └────────────────────────────────────────────────────────────────────┘
    └── 产出：信号 DataFrame (date/code/signal/confidence) + 仓位 DataFrame
  │
  ▼
[5] src/risk/
    rules.py            Rule ABC + RuleContext（规则数据总线）
    rule_engine.py      RuleEngine（按 priority 排序的链式执行引擎）
    rule_registry.py    风险规则名称 → 类映射
    position_limit.py   PositionLimitRule(150)
    tradability.py      TradabilityRule(200) / T1Rule(210)
    └── 产出：过滤后的信号 + 风控约束后的仓位
  │
  ▼
[6] src/backtest/                        [7] src/visualization/
    engine.py                             charts.py
    BacktestEngine(capital,               plot_equity_curve()
      stop_loss, take_profit,             plot_drawdown()
      trading_cost,                       plot_backtest_summary()
      circuit_breaker).run()
    └── 产出：trades + equity_curve
         + performance metrics
```

### Context 层决策流

```
行情数据
  │
  ├──▶ detect_regime()          ──▶ "trend_up" / "trend_down" / "range" / "volatile"
  │       │
  │       ├──▶ route_params(regime)     ──▶ {rebalance, top_n, bottom_n}
  │       │                                     │
  │       └──▶ RegimeSwitchStrategy            │
  │              ├─ trend_up  → gtja_momentum  │
  │              ├─ trend_down → reversed_vwap │
  │              ├─ range      → reversed_vwap │
  │              └─ volatile   → gtja_vol      │
  │                                             │
  │       strategy.generate_signal(data, **params)  ◀── 参数注入
  │
  └──▶ evaluate_factors()       ──▶ 季度级：因子 stability/coverage/dispersion 审计
        evaluate_factors_by_regime()  按 regime 分组的审计（诊断用，不接入主管道）
        select_tradable()      ──▶ 日频级：因子质量达标 → 动态股票池
```

### DrawdownCircuitBreaker 决策流

```
每日净值 (equity)
  │
  ├──▶ 计算 drawdown = (equity - peak) / peak
  │       │
  │       ├──▶ drawdown > threshold (-35%)  ──▶ exposure 渐进压缩至 min_exposure
  │       │       │
  │       │       └──▶ 3 日净值反弹 > 5%?  ──▶ Fast Recovery: exposure 重置 1.0
  │       │
  │       └──▶ drawdown < recovery (-15%)  ──▶ exposure 渐进恢复至 1.0
  │
  └──▶ Dead-Zone: |new_exposure - current| > 0.05 时才调整持仓
          │
          └──▶ 按 exposure 比例压缩 target shares → engine 按比例减仓
```

## 经验教训

经过大量回测验证后的发现：

- **A 股大市值股票年化收益天花板约 12-15%**，10 年期 Sharpe 天花板约 0.6
- **3 年回测不可信**。2023-2026 科技牛市虚高所有 Sharpe 50-70%。必须 ≥10 年验证。仅 3/11 行业在 3y 和 10y 下最优策略一致
- **gtja_momentum 是唯一跨周期稳定的策略**，3y 和 10y 都排第一，10y Sharpe 0.34
- **reversed_gtja_vwap 是 3y 过拟合典型**：Sharpe 1.11 → 10y 崩塌到 0.30
- **A 股有效信号是资金流，不是统计相关**：#118 上下影线比（日内多空战斗）和 #178 日收益×量（价格量能背书）单独跑赢 3 因子基线
- **5 因子组合是 sweet spot**：太少缺分散，太多稀释信号（18f < 5f）
- **因子稳定性排名跨 regime 高度一致**：VWAP 和 ATR 系列在任何行情下都是 top performer，rank correlation 类因子在任何行情下都是噪声
- **RegimeSwitch 的价值在极端行情避险**，日常平替 baseline，但暴跌时能少亏 24%
- **per-regime 因子权重切换增量极小**，参数路由（rebalance/top_n per regime）更有意义
- **DrawdownCircuitBreaker 降低 MaxDD 但不提升 Sharpe**：阈值 -35% 可将 MaxDD 从 -33.4% 压到 -27.8%，但 Sharpe 从 0.611 降到 0.535。CB 的价值在风控（MaxDD），不在收益（Sharpe）
- **A 股滑点注意**：market_data 的 limit_up/limit_down 是 bool 标志（是否涨停），不是价格。_apply_slippage 必须做类型检查，否则 min(price, False)=0

## 当前路线图

| # | 组件 | 状态 | 文件 |
|---|------|------|------|
| 1 | Regime 检测 | ✅ | [regime.py](src/context/regime.py) |
| 2 | Regime Switch | ✅ | [regime_switch.py](src/context/regime_switch.py) |
| 3 | 股票选择器 | ✅ | [stock_selector.py](src/context/stock_selector.py) |
| 4 | 参数路由 | ✅ | [param_router.py](src/context/param_router.py) |
| 5 | Circuit Breaker | ✅ | [circuit_breaker.py](src/portfolio/circuit_breaker.py) |
| 6 | Execution 模块 | 🔲 | 统一下单接口（模拟/实盘） |

## 快速开始

```bash
git clone <this-repo>
cd yoyo-quant
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest  # 1007 tests
```

## 命令行工具（yq）

安装后（`pip install -e .`）可用 `yq` 命令，或任意目录 `python -m yq`。

```bash
yq --help                 # 顶层帮助

# 因子注册表查询（支持 --tag/--kind 过滤，--json 输出结构化；--verbose 附带因子介绍）
yq factor list
yq factor list --kind pair --json
yq factor list --verbose --tag momentum

# 单因子计算（结果与输入逐行对齐，--param k=v 可重复传参）
yq factor run calc_obv --input data.parquet --output obv.parquet
yq factor run calc_rsi --input data.parquet --param window=14 --json

# IC/IR + 分层评估（多因子批量比较表）
yq factor evaluate --input factors.parquet --price price.parquet \
    --factor calc_rsi --factor calc_hv --window 1 --window 5 --window 20

# 因子磁盘缓存统计 / 清理
yq cache info
yq cache clear --factor calc_hv
```

IC/IR 因子筛查一键脚本（列出因子与介绍 + 单因子 + 多因子批量比较表，
默认合成数据可复现，`--data` 换真实行情）：

```bash
python notebooks/icir_factor_screening.py
python notebooks/icir_factor_screening.py --data data/clean/ohlcv.parquet --factor calc_hv

所有命令默认输出终端表格，加 `--json` 输出合法 JSON（NaN → null），方便脚本与 notebook 消费。因子数据输入为 parquet（date/code/close 等列），不绑定特定目录。

需要在 `.env` 中配置 `TUSHARE_TOKEN`。单元测试不依赖外部 API。

## 目录

```
yoyo-quant/
├── src/
│   ├── analysis/         # param_sweep + pipeline_diagnostics + pool_matrix
│   ├── backtest/         # engine + rqalpha adapter + walk_forward
│   ├── config/           # YAML loader + build functions
│   ├── context/          # regime + regime_switch + stock_selector + param_router
│   ├── data/             # fetcher + storage + filters + universe
│   ├── execution/        # unified order interface (mock/live)
│   ├── factors/          # operators(11) + 注册表(93 条目) + evaluation + cache + cointegration
│   ├── portfolio/        # equal_weight allocator + circuit_breaker
│   ├── risk/             # rules + rule_engine + rule_registry + tradability
│   ├── strategies/       # base + combiner + registry + reversed + builtin/(13 strategies)
│   ├── visualization/    # charts
│   └── yq/               # CLI: factor list/run/evaluate + cache info/clear
├── tests/                # 1007 tests (mirrors src/ structure)
├── tests_pipeline/       # cross-module pipeline tests
├── tests_integration/    # real API (skips without token)
├── notebooks/            # exploration + factor audit + CB comparison
├── configs/              # YAML configuration
├── docs/                 # project-plan.md + history.md + data-schemas.md
└── CLAUDE.md             # development conventions
```

## 开发规范

铁律：模块解耦、绝对 TDD、技术栈先行、禁止在生产代码使用 mock。

详细规范见 [CLAUDE.md](CLAUDE.md)。项目状态见 [docs/project-plan.md](docs/project-plan.md)，历史记录见 [docs/history.md](docs/history.md)。
