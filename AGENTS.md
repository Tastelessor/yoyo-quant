# yoyo-quant 开发规范

## 铁律（全局硬约束）
1. 模块解耦：通过接口交互，不依赖实现细节
2. 绝对TDD：先写测试再写实现
3. 技术栈先行：先定义契约再填实现
4. 禁止在生产代码使用mock

## 重构规范
涉及跨模块职责移动时，必须走完以下流程：
1. **查耦合**：grep 确认依赖面，评估影响范围
2. **改实现**：移动代码，调整函数签名（如 risk 层接收已标注数据，不再自己调 data 层）
3. **拆测试**：测试跟着实现走，按新模块边界拆分
4. **更新契约**：同步更新 data-schemas.md、__init__.py 导出、project-plan.md、history.md 函数引用
5. **跑测试**：确认全部通过

## 规则引擎规范

### 架构
- 所有风控规则继承 `Rule` ABC 基类（`src/risk/rules.py`）
- 规则通过 `RuleContext` 数据总线通信，不直接依赖其他规则
- `RuleEngine` 只负责按 priority 排序执行，不含业务逻辑

### 优先级分区
| 区域 | 范围 | 说明 |
|------|------|------|
| 信号生成 | 0-99 | 策略层规则 |
| 风控过滤 | 100-199 | 止损、仓位限制 |
| 交易约束 | 200-299 | T+1、涨跌停 |

新规则加入时选一个区域即可，区域内按注册顺序执行。

### 规则编写约定
- 每个规则必须设置 `name` 和 `priority`
- `apply()` 必须返回更新后的 `RuleContext`，不能返回 None
- 规则间通过 `ctx.metadata` 传递额外信息，不能直接调用其他规则
- 原有独立函数（如 `apply_position_limit`）保留不删除，Rule 子类内部调用它们

### 修改注意事项
- 新增规则：实现 Rule ABC，写测试，选好 priority 区域
- 修改现有规则：不能改变 apply() 的输入输出契约
- 修改引擎：极度谨慎，引擎应该是最稳定的组件
- 跨规则依赖：必须通过 ctx.metadata，不能 import 其他规则

## 策略框架规范

### 架构
- 所有策略继承 `Strategy` ABC 基类（`src/strategies/base.py`）
- 策略通过注册表（`src/strategies/registry.py`）按名获取
- 信号组合器（`src/strategies/combiner.py`）支持加权投票和层级过滤

### 策略编写约定
- 实现 `name` 属性和 `generate_signal(data, factors=None)` 方法
- 返回 DataFrame（date, code, signal, confidence），signal 为 int（1/-1/0）
- 用 `@register_strategy("name")` 装饰器注册
- 原有独立函数（如 `mean_reversion_signal`）保留不删除，Strategy 子类内部调用它们
- 具体策略放在 `strategies/builtin/`，框架代码在 `strategies/` 顶层

### 配置系统
- YAML 配置文件在 `configs/` 目录
- `load_config(path)` 加载并验证
- `build_strategies(cfg)` 从配置构建策略/组合器
- `build_risk_engine(cfg)` 从配置构建规则引擎
- 风险规则通过 `src/risk/rule_registry.py` 注册，名称映射到 Rule 子类

## 开工前检查
- **每个新 phase 开始前**，先 invoke `karpathy-guidelines` skill，读完再写代码
- Phase 1 教训：浮点精度、pandas API 返回类型、NumPy vs Python 类型——全是 Karpathy 警告过的坑

## 经验教训（详情见 README.md）
- A 股大市值年化收益天花板约 12-15%，10y Sharpe 天花板约 0.6；3 年回测不可信，必须 ≥10 年验证
- gtja_momentum 是唯一跨周期稳定策略；reversed_gtja_vwap 是 3y 过拟合典型（Sharpe 1.11 → 10y 0.30）
- A 股有效信号是资金流而非统计相关（#118 上下影线比、#178 日收益×量单跑赢 3 因子基线）
- 滑点处理坑：limit_up/limit_down 是 bool 标志（是否涨停），不是价格，_apply_slippage 必须做类型检查，否则 min(price, False)=0

## 环境
- Python >= 3.11
- 依赖管理：`pip install -e .`（或 `pip install -e ".[dev]"` 安装开发依赖）
- 格式化/Lint：`ruff format` + `ruff check`

## 测试

### 基础
- 框架：pytest
- 命名：`test_<module>.py`
- 覆盖率：暂不强制，但每个模块至少有接口测试
- 外部依赖（tushare、rqalpha）在单元测试中必须 mock，不依赖网络

### 目录与运行
- 单元测试：`tests/`，运行 `pytest`（pyproject.toml 的 testpaths=["tests"]，所以裸 `pytest` 只跑单元测试；快速，无外部依赖）
- 管道测试：`tests_pipeline/`，运行 `pytest tests_pipeline/`（模块间串联，mock 外部 API）
- 集成测试：`tests_integration/`，运行 `pytest tests_integration/`（需真实 API token，无 token 自动跳过）

### 何时写/改测试
- **新模块/函数**：TDD，先写测试再写实现
- **修 bug**：先补一个复现 bug 的测试，再修
- **改契约**（schema、函数签名、返回类型）：同步改测试
- **新增外部 API 调用**：在 `tests_integration/` 补集成测试
- **跨模块改动**：在 `tests_pipeline/` 补管道测试，验证模块间数据流

### 管道测试必须覆盖的场景
1. **完整管道**：data→factors→strategies→risk 全链路输出结构合法
2. **多股票独立性**：管道中各股票独立计算，不互相污染
3. **市场状态传导**：涨停/停牌标注能正确传导到信号过滤

### 单元测试必须覆盖的场景
1. **正常路径**：符合预期输入，输出结构和值正确
2. **边界条件**：空 DataFrame、单条数据、窗口不足（NaN 填充）
3. **类型断言**：返回类型（Series/DataFrame）、列 dtype（datetime64、float64、int、bool）
4. **多实体**：多只股票分别计算，不互相污染
5. **异常路径**：缺少必要列应抛 ValueError、缺少 token 应报错
6. **排序/去重**：输出按 date 排序、无意外重复行

### 集成测试必须覆盖的场景
1. **API 可达**：真实调用能返回非空数据
2. **字段匹配**：返回的列名严格匹配 OHLCV_SCHEMA
3. **类型正确**：date 为 datetime64、ohlcv 为数值、code 为字符串
4. **无空值**：核心字段无 NaN
5. **多市场**：深市（000001）和沪市（600519）都能正确获取

## 模块契约

### data 模块
- 输入：股票代码、日期范围、数据类型
- 输出：标准化 DataFrame（columns、dtypes 见 docs/data-schemas.md）
- 职责：获取、清洗、存储行情数据，并标注市场状态（涨跌停、停牌等布尔列）
- 数据源：tushare（`TUSHARE_TOKEN` 需在 `.env` 中配置）
- 存储：parquet 格式，路径 data/raw/（原始）和 data/clean/（清洗后）
- 内存约束：禁止全量加载，使用分块处理

### factors 模块
- 输入：data 模块输出的 DataFrame
- 输出：每个因子函数返回 pd.Series，由调用方组装成因子 DataFrame
- 职责：计算衍生指标（HV、IV、PCR、波动率锥等）
- **列名参数无关**：用 `hv` 而非 `hv_20`，参数通过配置传入，缓存键带参数哈希。详见 `docs/data-schemas.md`

### strategies 模块
- 输入：factors 模块输出的 DataFrame
- 输出：信号 DataFrame（含 signal, confidence 等字段）
- 职责：生成交易信号，不含仓位逻辑

### portfolio 模块
- 输入：信号 DataFrame + 风控约束
- 输出：目标仓位 DataFrame（schema 见 docs/data-schemas.md）
- 职责：仓位分配、再平衡

### risk 模块
- 输入：当前持仓 + 市场数据（含 data 层标注的市场状态列）
- 输出：风控约束 DataFrame + 过滤后的信号（schema 见 docs/data-schemas.md）
- 职责：定义和执行风险规则，包括可交易性约束（涨跌停/停牌过滤、T+1）

### backtest 模块
- 输入：信号/仓位 + 行情数据
- 输出：回测结果 DataFrame + 绩效指标 dict（schema 见 docs/data-schemas.md）
- 职责：模拟交易、计算绩效

### execution 模块（🔲 未实现，见 project-plan.md）
- 输入：目标仓位 DataFrame
- 输出：订单状态 DataFrame（schema 见 docs/data-schemas.md）
- 职责：统一下单接口（模拟/实盘）

### visualization 模块
- 输入：回测结果、持仓数据、因子数据
- 输出：图表和报告
- 职责：数据可视化（现阶段静态图）

### config 模块
- 职责：YAML 配置加载（`src/config/loader.py`：load_config / build_strategies / build_risk_engine / build_regime_switch）
- 配置文件在 `configs/`（default.yaml、production.yaml、csi500.yaml、full_market.yaml 等）

### context 模块（市场感知层，先于策略执行）
- regime.py：detect_regime → trend_up/trend_down/range/volatile
- regime_switch.py：RegimeSwitchStrategy 按 regime 路由子策略
- param_router.py：per-regime 参数路由（rebalance/top_n）
- stock_selector.py：因子质量评估 → 动态股票池
- 只做路由/筛选，不含信号生成逻辑（信号归 strategies 层）

### analysis 模块（诊断工具，不接入主管道）
- param_sweep.py：参数网格扫描
- pipeline_diagnostics.py：管道诊断
- pool_matrix.py：策略×行业交叉回测

### 数据流
```
                ┌→ backtest（模拟评估）
data → factors → strategies → portfolio → risk ─┤
                └→ execution（实盘/模拟盘）      ↓
                                            visualization
```
- 回测路径：data → factors → strategies → portfolio → risk → backtest → visualization
- 实盘路径：data → factors → strategies → portfolio → risk → execution → visualization
- 单向，无循环依赖
- **职责边界**：data 层只标注市场状态（涨跌停、停牌等布尔列），不做信号过滤；risk 层消费这些状态列，执行交易规则（filter_tradable、enforce_t1）

## 内存管理（16GB RAM，可用 ~7.8GB）
- 禁止全量加载：不一次性读入整个数据集
- 分块处理：chunksize 或按日期范围分段
- 回测时按时间窗口滑动加载
- 数据处理函数返回迭代器或分块结果

## 项目计划
- 当前状态：`docs/project-plan.md`（架构概览 + 模块状态表 + 目录结构）
- 历史记录：`docs/history.md`（已完成 Phase 的详细任务、回测结果、决策记录）
- 执行方式：每个 phase 开始时读取 project-plan.md 了解全局状态，用 TodoWrite 拆出当前 phase 的具体 task
- 完成 task 后更新 project-plan.md 状态表，详细变更记录到 history.md
- 重大方向调整时更新 history.md 决策记录

## 代码规范
- 类型注解：鼓励但暂不强制 mypy
