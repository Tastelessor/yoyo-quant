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
4. **更新契约**：同步更新 data-schemas.md、__init__.py 导出、project-plan.md 函数引用
5. **跑测试**：确认全部通过

## 开工前检查
- **每个新 phase 开始前**，先 invoke `karpathy-guidelines` skill，读完再写代码
- Phase 1 教训：浮点精度、pandas API 返回类型、NumPy vs Python 类型——全是 Karpathy 警告过的坑

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
- 单元测试：`tests/`，运行 `pytest`（快速，无外部依赖）
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

### execution 模块
- 输入：目标仓位 DataFrame
- 输出：订单状态 DataFrame（schema 见 docs/data-schemas.md）
- 职责：统一下单接口（模拟/实盘）

### visualization 模块
- 输入：回测结果、持仓数据、因子数据
- 输出：图表和报告
- 职责：数据可视化（现阶段静态图）

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
- 计划文件：`docs/project-plan.md`（架构概览 + 阶段任务 + 进度跟踪 + 决策记录）
- 执行方式：每个 phase 开始时读取 project-plan.md，用 TodoWrite 拆出当前 phase 的具体 task
- 完成 task 后更新 project-plan.md 中的 checkbox 和状态表
- 重大方向调整时更新决策记录

## 代码规范
- 类型注解：鼓励但暂不强制 mypy
