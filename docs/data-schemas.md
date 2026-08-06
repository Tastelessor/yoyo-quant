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
| pre_close | float64 | 前收盘（tushare 官方值，除权除息日已调整；由 `fetch_daily` / `fetch_index_daily` 返回，`detect_limit_price` 优先使用，缺失时回退 shift(1)） |
| volume | float64 | 成交量 |
| limit_up | bool | 涨停标记（由 data.filters.detect_limit_price 标注；按板块区分幅度：创业板/科创板 300/301/302/688/689 为 20%，其余 10%） |
| limit_down | bool | 跌停标记（同 limit_up） |
| is_suspended | bool | 停牌标记（由 data.filters.detect_suspension 标注：volume==0 或交易日网格中缺失的行；停牌日会补齐为一行，OHLCV 为 NaN） |

> 清洗入口：`data.clean.clean_market_data(df, trade_dates=None)` 一次完成三列标注
> （detect_suspension → detect_limit_price），输出按 (code, date) 排序、无重复行。

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

### 因子结果缓存（factors/ops/cache.py）

- 位置：`data/factors/{因子名}/{参数哈希}_{数据指纹}.parquet`（目录可用 `FACTOR_CACHE_DIR` 环境变量覆盖）。
- 缓存键 = (因子名, 参数哈希, 数据指纹)：调参、数据范围/内容变化均不命中旧缓存；数据指纹基于排序后非 date/code 列的内容哈希，与行顺序无关。
- 原子写（tmp + rename）；`clear_factor_cache(name=None, cache_dir=None)` 可清理；`run_factor(..., use_cache=False)` 禁用。

### 因子评估（factors/ops/evaluation.py）

> 因子预测力的标准化评估工具（IC / IR / forward return / 分层回测），纯 DataFrame 输出，不依赖交易管线与绘图库。输入 `factor_df`（宽表，含 date/code/因子列，任意行序）+ `price_df`（date/code/close，可省略——缺省从 factor_df 的 close 列取）；**所有返回与输入逐行对齐**。

| 函数 | 输出 | 说明 |
|------|------|------|
| `compute_forward_returns(price_df, windows=(1,5,20), exclude_untradable=False)` | `{window: Series}` | 按 code 分组的 N 数据行前向收益率；exclude 时 limit_up/limit_down/is_suspended 行置 NaN |
| `compute_ic(factor_df, name, fwd_ret, method="spearman", min_obs=5)` | Series（index=date，name=`{factor}_ic`） | 每日截面 IC 时序；spearman/pearson/kendall；有效样本 < min_obs 的日期跳过 |
| `compute_ir(ic_series)` | float | IR = IC 均值 / IC 标准差（ddof=1）；<2 值 NaN，恒定 IC 为 inf |
| `compute_rolling_ic(ic_series, window, min_periods=None)` | Series | 滚动窗口 IC 均值（`rolling(window).mean()`），index 与输入一致；min_periods=None 时窗口须填满 |
| `compute_rolling_ir(ic_series, window, min_periods=None)` | Series | 滚动 IR = 滚动均值/滚动标准差（ddof=1）；std=0 → inf，与 `compute_ir` 语义一致 |
| `compute_rolling_tstat(ic_series, window, min_periods=None)` | Series | 滚动 t 统计量 = 滚动 IR × √n（n=窗口内有效样本数），与窗口长度解耦；std=0 → inf |
| `compute_quantile_returns(factor_df, name, fwd_ret, n_quantiles=5, rebalance_days=None)` | dict | 每日分位分层等权组合：`quantile_returns`（q1..qn 宽表）/ `summary`（mean_return/std_return/hit_rate）/ `long_short`（qn-q1 价差）；rebalance_days=N 时每 N 行取一个调仓日 |
| `evaluate_factor(factor_df, name, price_df=None, ...)` | dict | 一站式：`ic`（DataFrame[window, ic_mean, ic_std, ic_ir, ic_positive_ratio]）/ `ic_series` / `quantiles` |
| `evaluate_factors(factor_df, names, price_df=None, ...)` | DataFrame | 批量比较表：`[factor, window, ic_mean, ic_std, ic_ir, ic_positive_ratio, ls_mean, ls_ir]`，每因子每窗口一行 |

### 因子生命周期监控（analysis/factor_monitor.py）

> 把因子评估升级为持续监控：对每 (factor, fwd_window) 的日频 IC 时序计算滚动 IC/IR/t 统计量，按双轨阈值（t 统计量为主、IR 参考线仅绘图）判定因子处于 active / decaying / dead / reverse 状态，支持尾部增量更新与状态持久化。输入为 data 模块行情（含 `limit_up`/`limit_down`/`is_suspended` 状态列，评估默认排除不可交易日）。

| 落盘 | 路径 | 说明 |
|------|------|------|
| state 长表 | `data/audit/factor_monitor/state.parquet` | 每 (date, factor, fwd_window) 一行的滚动统计快照；运行前自动备份为 `state.bak.parquet` |
| changes | `data/audit/factor_monitor/changes.parquet` | 本次运行发生的状态切换（无切换不落盘） |
| 图 | `data/audit/factor_monitor/figures/` | `health_heatmap.png`（全因子总览）+ `lifecycle_{factor}_fwd{w}.png`（单因子双轴时序） |

**state 表**（`STATE_COLS`）：`[date, factor, fwd_window, ic, rolling_ic, rolling_ir, t_stat, state, sustain_days]`

| 字段 | 类型 | 说明 |
|------|------|------|
| date | datetime64 | 统计日 |
| factor | str | 因子名（registry 动态发现，不硬编码列表） |
| fwd_window | int | forward 收益窗口（交易日数） |
| ic | float64 | 当日截面 IC（spearman） |
| rolling_ic | float64 | 滚动窗口 IC 均值（默认 window=60 交易日） |
| rolling_ir | float64 | 滚动 IR（mean/std，ddof=1；std=0 → inf） |
| t_stat | float64 | 滚动 t 统计量 = IR × √n；判定主输入（\|t\|>2 活跃、<1 失效、中间维持） |
| state | str | `active` / `decaying` / `dead` / `reverse`（t 反向显著时） |
| sustain_days | int | 当前状态连续持续交易日数（≥ min_sustain 才允许切换，防抖） |

**changes 表**（`CHANGE_COLS`）：`[date, factor, fwd_window, old_state, new_state]`

**CLI**：`yq factor monitor --data <ohlcv.parquet> [--factor 名 可重复] [--windows 5] [--window 60] [--min-sustain 20] [--min-obs 5] [--t-active 2.0] [--t-decay 1.0] [--ir-active-line 0.7] [--ir-dead-line 0.3] [--full] [--no-cache] [--output-dir] [--json]`
- 首次运行全量计算；之后默认只重算尾部（`state.parquet` 记录的历史之后）；`--full` 全量重算
- 输出状态摘要表（每 factor×fwd_window 一行，dead 置顶）与本次状态切换 diff

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

## 行业中性化 — factors.ops.neutralize 模块

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

## Phase A 因子相关性去冗余 — factors.ops.correlation 模块

> 纯函数、无状态；输入宽表（date/code/因子列）或相关矩阵；不依赖交易管线。

| 函数 | 输出 | 说明 |
|------|------|------|
| `compute_corr_matrix(factor_df, factors, *, window=60, method="spearman", agg="mean", min_obs=20)` | DataFrame（对称，index=columns=factors） | 取最近 window 个交易日，逐日截面 spearman 相关后按 agg 聚合；对角 1.0，数据不足 NaN |
| `cluster_redundant(corr_matrix, *, threshold=0.7, linkage_method="ward")` | DataFrame（factor/cluster_id） | 距离=1-|ρ|，scipy ward 层次聚类，距离空间阈值 1-threshold 剪枝；NaN 按 1.0 |
| `select_representative(cluster_df, stats, *, by="t_stat")` | DataFrame（cluster_id/representative/members/member_count） | 每簇取 t_stat/ir/combined（rank 均值）最大者；并列取字典序小者 |

### Phase A 编排 — analysis.factor_clean.run_phase_a

- 输入：state.parquet（monitor 长表）+ 全市场 ohlcv parquet
- 候选：最新日期 state ∈ {active, decaying} 且 fwd_window 匹配的因子；run_factor KeyError（缺列）→ skipped
- 输出 dict：as_of / factors / skipped / corr_matrix / clusters / representatives；output_dir 写 parquet + JSON + PNG
- 配置：`configs/factor_clean.yaml`（load_factor_clean_config，默认 corr_threshold=0.7 / corr_window=60 / cluster_linkage=ward / representative_by=t_stat）
- CLI：`yq factor clean-a --state ... --data ... [--config factor_clean.yaml] [--window 60] [--threshold 0.7] [--linkage ward] [--by t_stat] [--fwd-window 5] [--no-cache] [--output-dir] [--json]`

## Phase B walk-forward OOS — factors.ops.oos 模块

> 纯函数、无状态，对齐 factors.ops.evaluation 契约风格；不 import backtest.walk_forward（避免回测链耦合），窗口语义与其一致：train 紧贴 test、滑窗步长 = test_months。

### 函数契约（factors/ops/oos.py）

| 函数 | 输出 | 说明 |
|------|------|------|
| `generate_oos_windows(dates, *, train_months=12, test_months=1)` | list[(DatetimeIndex, DatetimeIndex)] | 每期 (train, test) 实际交易日；严格不相交、train 紧贴 test；test 终点超出数据末日的期不产生 |
| `select_top_factors(stats, top_k, *, min_t=None)` | list[str] | 按 \|t_stat\| 降序取 top_k；min_t 给定时过滤 \|t\| < min_t；t_stat 为 NaN 的因子恒被剔除（不参与排序选择） |
| `compute_test_period_stats(ic_series, *, min_days=5)` | dict（ic_mean/ic_t/ic_n/sig） | ic_t = mean/std×√n；std=0 或恒等 → ic_t=inf/sig=True；n<min_days → ic_t=NaN/sig=False；sig = \|ic_t\|>2 |
| `bootstrap_t_distribution(ic_series, n_iters, t_window, *, seed=None)` | ndarray（n_iters） | 路径②零分布：拟合 AR(1)（IC_t = c+φ·IC_{t-1}+ε）→ 残差中心化 → 打乱残差 → 无截距重建序列（起点 0，均值归 0）→ 尾部 t_window 样本的 t（与 monitor 滚动 t 同口径）；保留 AR 自相关结构（φ 大 → 零分布更肥尾）；输入不足 t_window 或 <3 点 → 全 NaN |

### Phase B 编排 — analysis.factor_oos.run_phase_b

- 输入：state.parquet（STATE_COLS 长表）+ ohlcv parquet（全市场行情）
- 每期：train 末 active/decaying × fwd_window → 因子值（run_factor，切片 [train 首日−LOOKBACK_MAX, test 末日+fwd_window]）→ 去冗余（train 末端 corr_window 天，correlation 纯函数）→ bootstrap 零分布 95 分位（**逐因子**：每因子用自己的 IC 序列跑路径②，不跨因子混合）→ 代表集 \|t\| > max(1, 因子自身 null_95) 按 \|t\| 降序 top_k → test 段重算 IC（exclude_untradable 默认开）→ 记录
- 输出 periods 长表列（15）：period_idx / train_start / train_end / test_start / test_end / factor / cluster_id / train_t / null_95 / selected / test_ic_mean / test_ic_t / test_ic_n / test_sig / win（null_95 为**该因子自身**的零分布 95 分位）
- summary 键：periods_total / periods_with_selection / periods_selected_total / overall_win_rate / overall_sig_rate / null_95_mean / period_win_rates（另含 train_months/test_months/top_k/bootstrap_iters/t_window 配置键）；null_95_mean = 全部因子自身 null_95 的均值
- output_dir 写：oos_results.parquet + oos_summary.json + oos_winrate.png + oos_bootstrap.png
- win = (train_t>0 and test_ic_t>2) or (train_t<0 and test_ic_t<-2)；test 期显著且方向保持；任一侧 NaN → False
- 配置：`configs/factor_clean.yaml` Phase B 段（oos_train_months=12 / oos_test_months=1 / top_k=5 / bootstrap_iters=200 / t_window=60），FACTOR_CLEAN_DEFAULTS 同步（11 项）
- CLI：`yq factor clean-b --state ... --data ... [--config] [--train-months] [--test-months] [--top-k] [--bootstrap-iters] [--t-window] [--window] [--threshold] [--linkage] [--by] [--fwd-window] [--seed] [--no-cache] [--output-dir] [--json]`
