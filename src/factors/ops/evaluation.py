"""Factor evaluation utilities: IC / IR / forward returns / quantile returns.

因子评估模块（infrastructure-todo P1-05）：为策略开发提供标准化的因子
预测力评估手段，输出纯 DataFrame / Series，不依赖交易管线与绘图库。

核心概念
--------
- **forward return**：因子值产生后未来 ``w`` 个数据行的收益率。
- **IC**（Information Coefficient）：每日截面上因子值与 forward return 的
  相关性（默认 RankIC / spearman），度量因子预测力。
- **IR**：IC 时序的均值 / 标准差，度量预测力的稳定性。
- **分层回测**：每日截面按因子值分位分层，比较各层组合收益与多空价差。

输入约定（与 ``calc_factors`` 输出兼容）
---------------------------------------
- ``factor_df``：宽表，含 ``date``、``code`` 与因子列，任意行序。
- ``price_df``：含 ``date``、``code``、``close`` 的市场数据，任意行序；
  省略时从 ``factor_df`` 的 ``close`` 列构造。
- 所有返回的 Series / DataFrame 均与输入逐行对齐（内部排序计算后映射回
  输入顺序），调用方无需自行排序。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WINDOWS: tuple[int, ...] = (1, 5, 20)
DEFAULT_UNTRADABLE_COLS: tuple[str, ...] = ("limit_up", "limit_down", "is_suspended")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_columns(df: pd.DataFrame, cols: tuple[str, ...], who: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{who} 缺少必要列: {missing}")


def _require_aligned_keys(factor_df: pd.DataFrame, price_df: pd.DataFrame) -> None:
    """factor_df 与 price_df 的 (date, code) 须逐行一致（对齐契约）。"""
    if len(factor_df) != len(price_df):
        raise ValueError(
            f"factor_df 行数 ({len(factor_df)}) 与 price_df 行数 ({len(price_df)}) "
            "不一致，无法逐行对齐"
        )
    a = factor_df[["date", "code"]].reset_index(drop=True)
    b = price_df[["date", "code"]].reset_index(drop=True)
    aligned = (
        a["date"].astype("datetime64[ns]").to_numpy()
        == b["date"].astype("datetime64[ns]").to_numpy()
    ) & (a["code"].to_numpy() == b["code"].to_numpy())
    if not aligned.all():
        raise ValueError(
            "factor_df 与 price_df 的 (date, code) 行序不一致；"
            "两者须按相同行序传入（评估返回与输入逐行对齐）"
        )


def _validate_pair(
    factor_df: pd.DataFrame, factor_name: str, forward_return: pd.Series
) -> None:
    _require_columns(factor_df, ("date", "code", factor_name), "factor_df")
    if not isinstance(forward_return, pd.Series):
        raise ValueError("forward_return 必须是 pd.Series")
    if len(factor_df) != len(forward_return):
        raise ValueError(
            f"factor_df 行数 ({len(factor_df)}) 与 forward_return 长度 "
            f"({len(forward_return)}) 不一致，需逐行对齐"
        )


# ---------------------------------------------------------------------------
# Forward returns
# ---------------------------------------------------------------------------


def compute_forward_returns(
    price_df: pd.DataFrame,
    windows: tuple[int, ...] | list[int] = DEFAULT_WINDOWS,
    *,
    exclude_untradable: bool = False,
    untradable_cols: tuple[str, ...] = DEFAULT_UNTRADABLE_COLS,
) -> dict[int, pd.Series]:
    """Compute forward returns for each window.

    Parameters
    ----------
    price_df : DataFrame
        行情数据，须含 ``date``、``code``、``close`` 列，任意行序。
    windows : tuple[int, ...] | list[int]
        前向收益窗口（数据行数），默认 ``(1, 5, 20)``。
    exclude_untradable : bool
        True 时，若数据含 ``limit_up`` / ``limit_down`` / ``is_suspended``
        等布尔列，当日任一列为 True 的行收益置 NaN。默认 False。
    untradable_cols : tuple[str, ...]
        不可交易标记列名，仅在数据中存在时生效。

    Returns
    -------
    dict[int, pd.Series]
        ``{window: Series}``，每个 Series 与 ``price_df`` 逐行对齐，
        name 为 ``fwd_ret_{w}d``。
    """
    _require_columns(price_df, ("date", "code", "close"), "price_df")
    for w in windows:
        if not isinstance(w, int) or w < 1:
            raise ValueError(f"window 必须为正整数，收到 {w!r}")
    tmp = price_df.assign(__pos__=range(len(price_df)))
    df_sorted = tmp.sort_values(["code", "date"]).reset_index(drop=True)
    orig_pos = df_sorted.pop("__pos__").to_numpy()
    back_order = np.argsort(orig_pos)

    result: dict[int, pd.Series] = {}
    for w in windows:
        # 按组 shift（fill_method=None 显式化，避免 pandas 2.0/2.1 默认差异）
        ret = df_sorted.groupby("code")["close"].transform(
            lambda s: s.pct_change(w, fill_method=None).shift(-w)
        )
        if exclude_untradable:
            cols = [c for c in untradable_cols if c in df_sorted.columns]
            if cols:
                mask = df_sorted[cols].any(axis=1)
                ret = ret.mask(mask)
        result[w] = ret.iloc[back_order].reset_index(drop=True).rename(f"fwd_ret_{w}d")
    return result


# ---------------------------------------------------------------------------
# IC / IR
# ---------------------------------------------------------------------------


def compute_ic(
    factor_df: pd.DataFrame,
    factor_name: str,
    forward_return: pd.Series,
    *,
    method: str = "spearman",
    min_obs: int = 5,
) -> pd.Series:
    """Compute daily cross-sectional IC between factor and forward return.

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date``、``code`` 与 ``factor_name`` 列。
    factor_name : str
        因子列名。
    forward_return : Series
        与 ``factor_df`` 逐行对齐的 forward return（见
        ``compute_forward_returns``）。
    method : str
        相关性方法，透传给 ``Series.corr``：``spearman`` / ``pearson`` /
        ``kendall``，默认 ``spearman``（RankIC）。
    min_obs : int
        单日截面有效样本数下限，低于该值的日期不出现在 IC 时序中。

    Returns
    -------
    Series
        index 为升序日期，name 为 ``{factor_name}_ic``。
    """
    _validate_pair(factor_df, factor_name, forward_return)
    if min_obs < 1:
        raise ValueError("min_obs 必须 >= 1")
    data = factor_df[["date", "code", factor_name]].copy()
    data["__fwd__"] = forward_return.to_numpy(dtype=float)

    ic_by_date: dict[pd.Timestamp, float] = {}
    for date, grp in data.groupby("date"):
        x = grp[factor_name].astype(float)
        y = grp["__fwd__"]
        mask = x.notna() & y.notna()
        if mask.sum() < min_obs:
            continue
        ic = x[mask].corr(y[mask], method=method)
        ic_by_date[date] = ic
    result = pd.Series(ic_by_date, dtype=float, name=f"{factor_name}_ic")
    return result.sort_index()


def compute_ir(ic_series: pd.Series) -> float:
    """Compute IR = mean(IC) / std(IC, ddof=1).

    少于 2 个有效值时返回 NaN；IC 恒定时（std=0）返回 ``inf``
    （预测力恒定，IR 无定义但非缺失）。
    """
    if len(ic_series) < 2:
        return float("nan")
    std = ic_series.std(ddof=1)
    if std == 0:
        return float("inf")
    return float(ic_series.mean() / std)


# ---------------------------------------------------------------------------
# Rolling IC / IR / t-statistic（因子生命周期监控）
# ---------------------------------------------------------------------------


def _validate_rolling_params(window: int, min_periods: int | None) -> int:
    if not isinstance(window, int) or window < 1:
        raise ValueError(f"window 必须为正整数，收到 {window!r}")
    mp = window if min_periods is None else min_periods
    if not isinstance(mp, int) or mp < 1:
        raise ValueError(f"min_periods 必须为正整数，收到 {mp!r}")
    return mp


def compute_rolling_ic(
    ic_series: pd.Series,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    """Compute rolling-window mean of a daily IC series.

    对 ``compute_ic`` 输出的日频 IC 时序做 ``rolling(window)`` 均值聚合，
    度量因子预测力的近期水平。

    Parameters
    ----------
    ic_series : Series
        日频 IC 时序（index 为升序日期，见 ``compute_ic``）。
    window : int
        滚动窗口（数据行数，>= 1）。
    min_periods : int | None
        窗口内有效值下限；None 时等于 ``window``（窗口须填满）。

    Returns
    -------
    Series
        滚动 IC 均值，index 与 ``ic_series`` 一致。
    """
    mp = _validate_rolling_params(window, min_periods)
    return ic_series.rolling(window=window, min_periods=mp).mean()


def compute_rolling_ir(
    ic_series: pd.Series,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    """Compute rolling IR = mean/std（ddof=1）over a window.

    度量预测力近期稳定性；窗口内 IC 恒定时（std=0）返回 ``inf``，
    与 ``compute_ir`` 语义一致。

    Parameters
    ----------
    ic_series / window / min_periods
        同 ``compute_rolling_ic``。

    Returns
    -------
    Series
        滚动 IR，index 与 ``ic_series`` 一致。
    """
    mp = _validate_rolling_params(window, min_periods)
    mean = ic_series.rolling(window=window, min_periods=mp).mean()
    std = ic_series.rolling(window=window, min_periods=mp).std(ddof=1)
    return mean / std  # std=0 → inf，与 compute_ir 一致


def compute_rolling_tstat(
    ic_series: pd.Series,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    """Compute rolling t-statistic = IR × √n（n = 窗口内有效样本数）。

    把滚动 IR 换算为显著性统计量，与窗口长度解耦（60 日窗口 IR=0.7 ↔
    t≈5.4），是状态机判定的主输入。

    Parameters
    ----------
    ic_series / window / min_periods
        同 ``compute_rolling_ic``；窗口含 NaN 时须显式调低 ``min_periods``
        让有效样本数足够（n 取窗口内有效数而非窗口长度）。

    Returns
    -------
    Series
        滚动 t 统计量，index 与 ``ic_series`` 一致；std=0 时为 ``inf``。
    """
    mp = _validate_rolling_params(window, min_periods)
    rolling = ic_series.rolling(window=window, min_periods=mp)
    mean = rolling.mean()
    std = rolling.std(ddof=1)
    n = rolling.count()
    return mean / std * np.sqrt(n)


# ---------------------------------------------------------------------------
# Layered IC panel（按 size × liquidity 层分组）
# ---------------------------------------------------------------------------


def compute_ic_by_layer(
    factor_df: pd.DataFrame,
    factor_name: str,
    forward_return: pd.Series,
    layer_df: pd.DataFrame,
    *,
    min_obs: int = 5,
    min_days: int = 10,
) -> pd.DataFrame:
    """全市场 + 按层分组的日频截面 IC 面板。

    Parameters
    ----------
    factor_df : DataFrame
        含 ``date`` / ``code`` / ``factor_name`` 列。
    forward_return : Series
        与 ``factor_df`` 行对齐的 forward return。
    layer_df : DataFrame
        含 ``date, code, size_layer, liq_layer``；按 ``(date, code)`` 与
        ``factor_df`` 对齐（行序无关）。
    min_obs : int
        单日单层截面有效样本下限（低于跳过当日）。
    min_days : int
        层有效天数下限；低于则 ``t_stat`` 为 NaN（n_days 仍记录）。

    Returns
    -------
    DataFrame
        index = ``["all"] + 9 层组合``（{size}-{liq}），列：
        mean_ic（IC 时序均值）、t_stat（mean/std×√n，std=0 → inf）、n_days。
    """
    merged = factor_df[["date", "code", factor_name]].copy()
    merged["__fwd__"] = forward_return.to_numpy(dtype=float)
    # 层标签按 (date, code) 对齐（行序无关，宽表与层表可能来自不同源）
    merged = merged.merge(
        layer_df[["date", "code", "size_layer", "liq_layer"]],
        on=["date", "code"],
        how="left",
    )

    def _stats(sub: pd.DataFrame) -> tuple[float, float, int]:
        ic = compute_ic(sub, factor_name, sub["__fwd__"], min_obs=min_obs)
        n = len(ic)
        if n == 0:
            return float("nan"), float("nan"), 0
        mean = float(ic.mean())
        t = float(compute_ir(ic) * np.sqrt(n))  # std=0 → inf（同 rolling_tstat 语义）
        return mean, t, n

    rows: dict[str, dict] = {}
    rows["all"] = dict(zip(("mean_ic", "t_stat", "n_days"), _stats(merged)))
    for size in ("small", "mid", "large"):
        for liq in ("low", "mid", "high"):
            sub = merged[
                (merged["size_layer"] == size) & (merged["liq_layer"] == liq)
            ]
            mean, t, n = _stats(sub)
            rows[f"{size}-{liq}"] = {"mean_ic": mean, "t_stat": t, "n_days": n}
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.loc[out["n_days"] < min_days, "t_stat"] = float("nan")
    return out[["mean_ic", "t_stat", "n_days"]]


# ---------------------------------------------------------------------------
# Quantile (layered) returns
# ---------------------------------------------------------------------------


def compute_quantile_returns(
    factor_df: pd.DataFrame,
    factor_name: str,
    forward_return: pd.Series,
    *,
    n_quantiles: int = 5,
    rebalance_days: int | None = None,
) -> dict:
    """Compute equal-weight quantile portfolio returns.

    Parameters
    ----------
    factor_df / factor_name / forward_return
        同 ``compute_ic``。
    n_quantiles : int
        分层数（>= 2），默认 5（quintile）。
    rebalance_days : int | None
        None（默认）时每日计算层收益；``N`` 时每 N 个数据行取一个调仓日，
        非调仓日的层收益为 NaN。

    Returns
    -------
    dict
        - ``quantile_returns``：DataFrame，index 为日期，列为 ``q1..q{n}``，
          值为该层当日 forward return 的截面均值。
        - ``summary``：DataFrame，列为 ``quantile / mean_return /
          std_return / hit_rate``，每层一行。
        - ``long_short``：DataFrame，列为 ``date / ls_return``，
          多空价差 = q{n} - q1。
    """
    _validate_pair(factor_df, factor_name, forward_return)
    if n_quantiles < 2:
        raise ValueError("n_quantiles 必须 >= 2")
    if rebalance_days is not None and rebalance_days < 1:
        raise ValueError("rebalance_days 必须 >= 1 或 None")

    data = factor_df[["date", "code", factor_name]].copy()
    data["__fwd__"] = forward_return.to_numpy(dtype=float)
    dates = pd.Index(sorted(data["date"].unique()))
    q_cols = [f"q{i}" for i in range(1, n_quantiles + 1)]
    qr = pd.DataFrame(np.nan, index=dates, columns=q_cols)

    for date, grp in data.groupby("date"):
        grp = grp.dropna(subset=[factor_name, "__fwd__"])
        n_valid = len(grp)
        if n_valid < n_quantiles:
            continue
        ranks = grp[factor_name].rank(method="first")
        labels = pd.qcut(ranks, n_quantiles, labels=False)
        for k in range(n_quantiles):
            qr.loc[date, q_cols[k]] = grp.loc[labels == k, "__fwd__"].mean()

    if qr["q1"].isna().all():
        raise ValueError(
            "无法分层：无任何日期有 >= "
            f"{n_quantiles} 个有效样本（n_quantiles={n_quantiles}）"
        )

    if rebalance_days is not None:
        keep = dates[::rebalance_days]
        qr.loc[~qr.index.isin(keep)] = np.nan

    summary_rows = []
    for col in q_cols:
        s = qr[col].dropna()
        summary_rows.append(
            {
                "quantile": col,
                "mean_return": s.mean() if len(s) else np.nan,
                "std_return": s.std(ddof=1) if len(s) > 1 else np.nan,
                "hit_rate": (s > 0).mean() if len(s) else np.nan,
            }
        )
    ls = pd.DataFrame(
        {"date": dates, "ls_return": (qr[q_cols[-1]] - qr[q_cols[0]]).values}
    )
    return {
        "quantile_returns": qr,
        "summary": pd.DataFrame(summary_rows),
        "long_short": ls,
    }


# ---------------------------------------------------------------------------
# One-stop / batch evaluation
# ---------------------------------------------------------------------------


def evaluate_factor(
    factor_df: pd.DataFrame,
    factor_name: str,
    price_df: pd.DataFrame | None = None,
    *,
    windows: tuple[int, ...] | list[int] = DEFAULT_WINDOWS,
    method: str = "spearman",
    min_obs: int = 5,
    n_quantiles: int = 5,
    rebalance_days: int | None = None,
    exclude_untradable: bool = False,
    untradable_cols: tuple[str, ...] = DEFAULT_UNTRADABLE_COLS,
) -> dict:
    """Evaluate a single factor across windows.

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date``、``code`` 与因子列；``price_df=None`` 时须含
        ``close`` 列。
    factor_name : str
        因子列名。
    price_df : DataFrame | None
        行情数据（date, code, close）。None 时从 ``factor_df`` 的 ``close``
        列构造。
    windows / method / min_obs / n_quantiles / rebalance_days /
    exclude_untradable / untradable_cols
        透传给 ``compute_forward_returns`` / ``compute_ic`` /
        ``compute_quantile_returns``。

    Returns
    -------
    dict
        - ``ic``：DataFrame，每窗口一行，列为 ``window / ic_mean /
          ic_std / ic_ir / ic_positive_ratio``。
        - ``ic_series``：``{window: Series}``，IC 时序。
        - ``quantiles``：``{window: dict | None}``，窗口无任何有效 forward
          return（超出数据长度）时为 None，见 ``compute_quantile_returns``。
    """
    if price_df is None:
        if "close" not in factor_df.columns:
            raise ValueError(
                "price_df 未提供且 factor_df 缺少 close 列；"
                "请传入 price_df 或使用含 close 的 factor_df"
            )
        price_df = factor_df[["date", "code", "close"]]
    else:
        _require_aligned_keys(factor_df, price_df)

    fwd = compute_forward_returns(
        price_df,
        windows=windows,
        exclude_untradable=exclude_untradable,
        untradable_cols=untradable_cols,
    )
    ic_rows: list[dict] = []
    ic_series: dict[int, pd.Series] = {}
    quantiles: dict[int, dict | None] = {}
    for w in windows:
        ic = compute_ic(factor_df, factor_name, fwd[w], method=method, min_obs=min_obs)
        ic_series[w] = ic
        ic_rows.append(
            {
                "window": w,
                "ic_mean": ic.mean(),
                "ic_std": ic.std(ddof=1),
                "ic_ir": compute_ir(ic),
                "ic_positive_ratio": (ic > 0).mean() if len(ic) else np.nan,
            }
        )
        if not fwd[w].notna().any():
            # 窗口超出数据长度：无任何有效 forward return，保留 NaN 行不抛错
            quantiles[w] = None
            continue
        quantiles[w] = compute_quantile_returns(
            factor_df,
            factor_name,
            fwd[w],
            n_quantiles=n_quantiles,
            rebalance_days=rebalance_days,
        )
    return {"ic": pd.DataFrame(ic_rows), "ic_series": ic_series, "quantiles": quantiles}


def evaluate_factors(
    factor_df: pd.DataFrame,
    factor_names: list[str],
    price_df: pd.DataFrame | None = None,
    *,
    windows: tuple[int, ...] | list[int] = DEFAULT_WINDOWS,
    method: str = "spearman",
    min_obs: int = 5,
    n_quantiles: int = 5,
    rebalance_days: int | None = None,
    exclude_untradable: bool = False,
    untradable_cols: tuple[str, ...] = DEFAULT_UNTRADABLE_COLS,
) -> pd.DataFrame:
    """Evaluate multiple factors and produce a comparison table.

    Returns
    -------
    DataFrame
        每因子每窗口一行，列为 ``factor / window / ic_mean / ic_std /
        ic_ir / ic_positive_ratio / ls_mean / ls_ir``；按 ``factor_names``
        顺序、window 升序排列。IC / 分层配置参数同上。
    """
    rows: list[dict] = []
    for name in factor_names:
        out = evaluate_factor(
            factor_df,
            name,
            price_df,
            windows=windows,
            method=method,
            min_obs=min_obs,
            n_quantiles=n_quantiles,
            rebalance_days=rebalance_days,
            exclude_untradable=exclude_untradable,
            untradable_cols=untradable_cols,
        )
        for w in windows:
            ic_row = out["ic"].loc[out["ic"]["window"] == w].iloc[0]
            q = out["quantiles"][w]
            if q is None:
                ls_mean, ls_ir = np.nan, np.nan
            else:
                ls = q["long_short"]["ls_return"]
                ls_mean = ls.mean() if len(ls) else np.nan
                ls_ir = compute_ir(ls)
            rows.append(
                {
                    "factor": name,
                    "window": w,
                    "ic_mean": ic_row["ic_mean"],
                    "ic_std": ic_row["ic_std"],
                    "ic_ir": ic_row["ic_ir"],
                    "ic_positive_ratio": ic_row["ic_positive_ratio"],
                    "ls_mean": ls_mean,
                    "ls_ir": ls_ir,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "factor",
            "window",
            "ic_mean",
            "ic_std",
            "ic_ir",
            "ic_positive_ratio",
            "ls_mean",
            "ls_ir",
        ],
    )
