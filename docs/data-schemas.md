# 数据结构契约

## 行情数据 (OHLCV) — data 模块输出

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 交易日期 |
| code | str | 股票代码 |
| open | float64 | 开盘价 |
| high | float64 | 最高价 |
| low | float64 | 最低价 |
| close | float64 | 收盘价 |
| volume | float64 | 成交量 |
| limit_up | bool | 涨停标记（由 data.filters.detect_limit_price 标注） |
| limit_down | bool | 跌停标记（由 data.filters.detect_limit_price 标注） |
| is_suspended | bool | 停牌标记（由 data.filters.detect_suspension 标注） |

## 因子数据 — factors 模块输出

> 每个因子函数（如 `calc_hv`）返回 `pd.Series`，由调用方组装成下表的 DataFrame。
> **参数无关设计**：列名不含参数值（用 `hv` 而非 `hv_20`）。参数通过配置传入，缓存键带参数哈希，避免调参时列名变动导致下游断裂。

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| code | str | 股票代码 |
| hv | float64 | 历史波动率（默认 20 日，可配置） |
| iv | float64 | 隐含波动率（期权标的） |
| pcr | float64 | 看跌看涨比 |
| rsi | float64 | RSI 相对强弱指标（默认 14 日，可配置） |
| obv | float64 | OBV 能量潮 |
| volume_ratio | float64 | 成交量比率（当前 / 均量，默认 20 日） |
| atr | float64 | ATR 平均真实波幅（默认 14 日，可配置） |
| spread | float64 | 配对价差（log(A) - beta*log(B)） |
| spread_zscore | float64 | 价差滚动 z-score |

## 信号数据 — strategies 模块输出

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 信号日期 |
| code | str | 股票代码 |
| signal | int | 1=买入, -1=卖出, 0=持有 |
| confidence | float64 | 信号置信度 0-1 |

## 仓位数据 — portfolio 模块输出

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| code | str | 股票代码 |
| weight | float64 | 目标权重 0-1 |
| shares | int | 目标股数 |

## 风控 — risk 模块输出

### 仓位调整（position_limit）

`apply_position_limit` 是仓位数据的变换器：输入仓位 DataFrame，输出同结构的调整后仓位。
输出 schema 与仓位数据相同（date, code, weight, shares）。

### 可交易性过滤（tradability）

`filter_tradable` / `enforce_t1` 是信号数据的变换器：输入信号 DataFrame，输出同结构的过滤后信号。
输出 schema 与信号数据相同（date, code, signal, confidence）。

### 风控约束报告（预留）

| 字段 | 类型 | 说明 |
|------|------|------|
| rule | str | 规则名称 |
| limit | float64 | 限制值 |
| current | float64 | 当前值 |
| breached | bool | 是否触发 |

## 回测结果 — backtest 模块输出

### 交易记录

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| code | str | 股票代码 |
| action | str | buy/sell/stop_loss/take_profit/atr_stop_loss |
| price | float64 | 执行价（含滑点） |
| shares | int | 成交股数 |
| pnl | float64 | 盈亏（扣除摩擦后） |
| cost | float64 | 本笔交易摩擦成本（佣金+印花税+过户费） |

### 权益曲线

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 日期 |
| equity | float64 | 总权益（cash + 持仓市值） |
| cash | float64 | 可用现金 |
| position_value | float64 | 持仓市值 |
| returns | float64 | 当日收益率 |

### 绩效指标

| 字段 | 类型 | 说明 |
|------|------|------|
| total_return | float64 | 总收益率 |
| annual_return | float64 | 年化收益率 |
| sharpe_ratio | float64 | 夏普比率（无风险利率默认 0.03） |
| max_drawdown | float64 | 最大回撤 |
| win_rate | float64 | 胜率（盈利退出交易 / 总退出交易） |
| trade_count | int | 总交易次数 |
| total_cost | float64 | 全部交易摩擦成本之和 |
| cost_ratio | float64 | 换手损耗率 = total_cost / turnover（turnover = 双向换手流水） |

## 订单状态 — execution 模块输出

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | str | 订单 ID |
| code | str | 股票代码 |
| side | str | buy/sell |
| price | float64 | 成交价 |
| shares | int | 成交股数 |
| status | str | pending/filled/cancelled/rejected |
| timestamp | datetime64 | 下单时间 |
