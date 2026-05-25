# yoyo-quant

A 股量化策略研究框架——从数据到回测的完整管道，专注系统性策略验证而非"看指标猜涨跌"。

## 当前能力

- **100 只 CSI 300 大市值股票**，覆盖 11 个行业板块
- **GTJA 191 因子库**：22+ 因子（动量/均值回归/量价/波动率/VWAP/趋势），7 个可复用算子
- **11 个策略**：6 个 GTJA 因子策略 + 均值回归/RSI 反转/动量突破/动量趋势/多因子
- **策略包装器**：ReversedStrategy（反向信号）、RegimeSwitchStrategy（市场状态自适应切换）
- **完整回测管道**：data → factors → strategies → portfolio → risk → backtest → visualization
- **风控引擎**：可组合规则引擎（止损/仓位限制/T+1/涨跌停过滤）
- **分析工具**：参数网格扫描、管道诊断、策略×行业矩阵交叉回测
- **447+ 测试**：单元测试 + 管道测试 + 集成测试

## 一年多的经验教训

经过大量回测验证后的一些发现：

- **A 股大市值股票年化收益天花板约 12-15%**，10 年期 Sharpe 天花板约 0.6。如果有人告诉你 A 股量化能做到年化 30%+ Sharpe 2.0，跑。
- **3 年回测结果不可信**。2023-2026 科技牛市让几乎所有策略看起来都不错。必须用 ≥10 年窗口验证。在我们的行业矩阵里，只有 3/11 个行业在 3y 和 10y 窗口下最优策略一致。
- **gtja_momentum 是唯一跨周期稳定的策略**，3y 和 10y 都排第一，但 10y Sharpe 也只有 0.34。
- **reversed_gtja_vwap 是 3y 窗口的冠军**（Sharpe 1.11），但在 10y 窗口崩塌到倒数第一。典型过拟合案例。
- **单因子类别不足以产生稳定 alpha**，所有 GTJA 策略 Sharpe < 0.5。信号质量才是根本问题，不是风控或组合优化。
- **RegimeSwitch 的价值在极端行情避险**，日常平替 baseline，但在市场暴跌时能少亏 24%。
- **半衰期比协整检验更实用**作为配对筛选指标——协整通过的对 hl=4000+ 天基本没法交易。
- **消费行业值得关注**——3y 窗口下死气沉沉，10y 窗口下 Sharpe 0.49（排第二）。均值回归需要长周期才能体现。

## 架构

```
              ┌→ backtest（模拟评估）
data → factors → strategies → portfolio → risk ─┤
              └→ execution（实盘/模拟盘）      ↓
                                          visualization
```

单向数据流，无循环依赖。每层有明确的 DataFrame schema 契约。

| 模块 | 职责 |
|------|------|
| `data` | 行情获取、清洗、存储、股票池管理 |
| `factors` | 衍生指标计算（GTJA 191 因子 + 基础量价因子） |
| `strategies` | 交易信号生成（Strategy ABC + 注册表 + 组合器 + 包装器） |
| `context` | 市场状态感知（regime 检测、策略路由） |
| `portfolio` | 仓位分配与再平衡 |
| `risk` | 风控规则引擎（Rule ABC + 链式执行 + 注册表） |
| `backtest` | 轻量回测引擎 + rqalpha adapter |
| `analysis` | 参数扫描、管道诊断、策略×行业矩阵 |
| `visualization` | 权益曲线、回撤图、绩效面板 |
| `config` | YAML 配置系统（策略构建 + 风控构建） |

## 快速开始

```bash
git clone <this-repo>
cd yoyo-quant
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest  # 447+ tests should pass
```

需要在 `.env` 中配置 `TUSHARE_TOKEN` 才能拉取真实行情数据。单元测试不依赖外部 API。

## 项目结构

```
yoyo-quant/
├── src/
│   ├── analysis/         # 参数扫描、管道诊断、矩阵分析
│   ├── backtest/          # 轻量回测引擎 + rqalpha adapter
│   ├── config/            # YAML 配置加载与构建
│   ├── context/           # 市场状态检测与策略路由
│   ├── data/              # 行情获取、存储、股票池
│   ├── execution/         # 下单接口（规划中）
│   ├── factors/           # GTJA 191 因子 + 基础量价因子 + 注册表
│   ├── portfolio/         # 仓位分配
│   ├── risk/              # 风控规则引擎 + 止损 + 可交易性
│   ├── strategies/        # 策略框架 + 内置策略 + 注册表 + 组合器
│   └── visualization/     # 图表与报告
├── tests/                 # 单元测试（镜像 src 结构）
├── tests_pipeline/        # 管道测试（模块间串联）
├── tests_integration/     # 集成测试（需真实 API）
├── notebooks/             # 探索分析
├── configs/               # YAML 配置文件
├── docs/                  # 技术文档（project-plan.md、history.md、data-schemas.md）
├── CLAUDE.md              # 开发规范（给 AI 协作看）
└── README.md
```

## 开发规范

铁律：模块解耦、绝对 TDD、技术栈先行、禁止在生产代码使用 mock。

详细规范见 [CLAUDE.md](CLAUDE.md)。项目状态和历史见 [docs/](docs/)。
