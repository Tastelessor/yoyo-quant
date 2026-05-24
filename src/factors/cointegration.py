"""协整检验与价差因子。

提供配对交易所需的价差计算、z-score、协整检验和半衰期估计。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


def calc_spread(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    beta: float | None = None,
) -> pd.Series:
    """计算两个股票的对数价差。

    spread = log(close_A) - beta * log(close_B)

    Parameters
    ----------
    df_a : DataFrame
        必须包含 date, close 列（单只股票）。
    df_b : DataFrame
        必须包含 date, close 列（单只股票）。
    beta : float or None
        对冲比率。None 时通过 OLS 回归估计。

    Returns
    -------
    Series
        以 date 为索引的价差序列。
    """
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date",
        how="inner",
    ).drop_duplicates(subset=["date"], keep="last").sort_values("date")

    log_a = np.log(merged["close_a"].values)
    log_b = np.log(merged["close_b"].values)

    if beta is None:
        # OLS: log_a = beta * log_b + alpha
        x = np.column_stack([log_b, np.ones(len(log_b))])
        coeffs, _, _, _ = np.linalg.lstsq(x, log_a, rcond=None)
        beta = coeffs[0]

    spread_values = log_a - beta * log_b
    return pd.Series(spread_values, index=merged["date"].values, name="spread")


def calc_spread_zscore(
    spread: pd.Series,
    window: int = 20,
) -> pd.Series:
    """计算价差的滚动 z-score。

    z = (spread - rolling_mean) / rolling_std

    Parameters
    ----------
    spread : Series
        价差序列（应以 date 为索引）。
    window : int
        滚动窗口大小。

    Returns
    -------
    Series
        z-score 序列，前 window-1 个值为 NaN。常数价差时全为 0。
    """
    rolling_mean = spread.rolling(window=window, min_periods=window).mean()
    rolling_std = spread.rolling(window=window, min_periods=window).std()

    zscore = (spread - rolling_mean) / rolling_std
    # 统一处理：NaN 和 inf 都置零
    zscore = zscore.fillna(0.0).replace([np.inf, -np.inf], 0.0)
    return zscore


def calc_coint_pvalue(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    min_obs: int = 60,
) -> float:
    """Engle-Granger 协整检验 p-value。

    检验两个价格序列的价差是否平稳。

    Parameters
    ----------
    df_a, df_b : DataFrame
        必须包含 date, close 列。
    min_obs : int
        最小观测数，不足时返回 1.0。

    Returns
    -------
    float
        p-value。低值（< 0.05）表示存在协整关系。
    """
    merged = pd.merge(
        df_a[["date", "close"]].rename(columns={"close": "close_a"}),
        df_b[["date", "close"]].rename(columns={"close": "close_b"}),
        on="date",
        how="inner",
    ).drop_duplicates(subset=["date"], keep="last").sort_values("date")

    if len(merged) < min_obs:
        return 1.0

    # 用 OLS 残差做 ADF 检验
    log_a = np.log(merged["close_a"].values)
    log_b = np.log(merged["close_b"].values)
    x = np.column_stack([log_b, np.ones(len(log_b))])
    coeffs, _, _, _ = np.linalg.lstsq(x, log_a, rcond=None)
    residuals = log_a - x @ coeffs

    # 残差为常数（完全协整）-> p-value = 0
    if np.std(residuals) < 1e-12:
        return 0.0

    try:
        _, pval, _, _, _, _ = adfuller(residuals, maxlag=None, autolag="AIC")
        return float(pval)
    except Exception:
        return 1.0


def calc_half_life(
    spread: pd.Series,
    window: int = 60,
) -> float:
    """估计 Ornstein-Uhlenbeck 过程的均值回复半衰期。

    使用 OLS 回归：delta_spread = lambda * spread_{t-1} + epsilon
    half_life = -log(2) / lambda

    Parameters
    ----------
    spread : Series
        价差序列。调用方应确保已按时间升序排列。
    window : int
        用于估计的观测数（取最后 window 个值）。

    Returns
    -------
    float
        半衰期（周期数）。负 lambda（均值回复）时为正值。
    """
    s = spread.dropna().values
    if len(s) < window + 1:
        return np.nan

    s = s[-window - 1 :]
    y = np.diff(s)
    x = s[:-1].reshape(-1, 1)

    coeffs, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    lam = coeffs[0]

    if lam >= 0:
        return np.nan  # 非均值回复

    return -np.log(2) / lam


def kalman_filter_hedge_ratio(
    log_a: np.ndarray,
    log_b: np.ndarray,
    q: float = 1e-5,
    r: float = 1e-3,
) -> np.ndarray:
    """Kalman Filter 估计动态对冲比率 beta。

    状态模型：beta_t = beta_{t-1} + w_t,  w ~ N(0, Q)
    观测模型：log(A)_t = beta_t * log(B)_t + v_t,  v ~ N(0, R)

    Parameters
    ----------
    log_a : ndarray
        log(close_A) 序列。
    log_b : ndarray
        log(close_B) 序列。
    q : float
        状态噪声方差（越大 beta 变化越快）。
    r : float
        观测噪声方差（越大越信任模型而非观测）。

    Returns
    -------
    ndarray
        beta 估计序列，长度与输入相同。
    """
    n = len(log_a)
    betas = np.zeros(n)

    # 初始状态：用前 10 个点的 OLS 估计
    init_window = min(10, n)
    x_init = np.column_stack([log_b[:init_window], np.ones(init_window)])
    coeffs, _, _, _ = np.linalg.lstsq(x_init, log_a[:init_window], rcond=None)
    beta = coeffs[0]
    P = 1.0  # 初始协方差

    for t in range(n):
        # 预测
        beta_pred = beta
        P_pred = P + q

        # 更新
        y = log_a[t] - beta_pred * log_b[t]
        S = P_pred * log_b[t] ** 2 + r
        K = P_pred * log_b[t] / S  # 卡尔曼增益
        beta = beta_pred + K * y
        P = (1 - K * log_b[t]) * P_pred

        betas[t] = beta

    return betas
