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

## 交易日历 — data 模块输出

> 权威交易日历接口（`src/data/trade_calendar.py`），数据源为 tushare `trade_cal`
> （沪深交易所官方日历）。PIT 面板（`build_earnings_panel` / `build_quality_panel`）
> 与回测的 trade_dates 网格必须来自本接口，**不得**用行情 `data["date"].unique()` 推断——
> 停牌日/节假日缺失会导致网格错位。
> 缓存：`data/raw/trade_cal/{exchange}.parquet`，一次全量拉取 [1990-01-01, 2030-12-31]。

### fetch_trade_calendar 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| exchange | str | 交易所代码（SSE/SZSE/CSSE），沪深 A 股用 SSE（与 SZSE 节假日一致） |
| cal_date | datetime64 | 日历日期（升序、无重复） |
| is_open | int | 1=开市, 0=闭市（周末/节假日） |
| pretrade_date | str | 上一交易日，格式 YYYYMMDD |

### 接口

| 函数 | 返回 | 说明 |
|------|------|------|
| `fetch_trade_dates(start, end, exchange="SSE")` | pd.DatetimeIndex | [start, end] 闭区间内交易日（is_open=1），升序无重复；区间无交易日返回空 |
| `is_trading_day(date, exchange="SSE")` | bool | 单日是否开市；周末/节假日/不在日历中返回 False |

无 `TUSHARE_TOKEN` 时抛 ValueError（与 data 模块其余 fetch 函数一致）。

## 因子数据 — factors 模块输出

> 每个因子函数（如 `calc_hv`）返回 `pd.Series`，由调用方组装成下表的 DataFrame。
> **参数无关设计**：列名不含参数值（用 `hv` 而非 `hv_20`）。参数通过配置传入，缓存键带参数哈希，避免调参时列名变动导致下游断裂。

### 注册表与调用方式

- 所有单股票因子（**kind="single"**）注册在 `src/factors/registry.py`，按名调用统一走 `run_factor(name, df, **params)` 或 `calc_factors(df, names, params={...})`；策略层禁止直接 import 因子函数。
- 配对专用因子（**kind="pair"**：`calc_spread` / `calc_spread_zscore` / `calc_coint_pvalue` / `calc_half_life` / `kalman_filter_hedge_ratio`）签名与单股票因子不同（双 DataFrame / Series / ndarray 输入，float/ndarray 输出），仅按名发现（`get_factor`），由调用方按配对接口直接调用，不参与 `run_factor` / `calc_factors`。
- 带参因子（`calc_rsi` / `calc_volume_ratio` / `calc_atr` / `calc_hv` 的 `window` 等）默认参数从函数签名自动提取，`run_factor` 时可用 kwargs 覆盖。

### 因子结果缓存（cache.py）

- 位置：`data/factors/{因子名}/{参数哈希}_{数据指纹}.parquet`（目录可用 `FACTOR_CACHE_DIR` 环境变量覆盖）。
- 缓存键 = (因子名, 参数哈希, 数据指纹)：调参、数据范围/内容变化均不命中旧缓存；数据指纹基于排序后非 date/code 列的内容哈希，与行顺序无关。
- 原子写（tmp + rename）；`clear_factor_cache(name=None, cache_dir=None)` 可清理；`run_factor(..., use_cache=False)` 禁用。

### 输出字段

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

## 行业中性化 — factors.neutralize 模块

> **Warning**: 当前使用 Tushare `stock_basic` 的最新行业分类快照（申万一级）。
> 在长期回测（如 2016-2026）中，公司行业分类可能已发生变更，存在近似前视偏差。
> 后续迭代应升级为 point-in-time 动态行业分类。

行业中性化通过 `neutralize_factors()` 实现，插入在策略层因子提取之后、rank 排名之前。

### neutralize_factors 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| factor_df | DataFrame | 必须含 date, code, 和因子列 |
| industry_map | dict[str, str] | code → 行业名映射 |
| factor_cols | list[str] | 要中性化的因子列名 |
| method | str | 中性化方法（目前仅 "demean"） |
| min_peers | int | 行业最小标的数，不足则降级到 __unknown__ 组 |

### neutralize_factors 输出

与输入 `factor_df` 结构相同，`factor_cols` 列被替换为去均值后的值。

### 配置

```yaml
neutralization:
  enabled: true
  method: demean
  min_peers: 3
```
