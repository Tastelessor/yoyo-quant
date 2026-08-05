"""配对交易策略。

基于价差 z-score 的均值回复策略。做多被低估的股票，做空被高估的股票。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.registry import get_factor
from strategies.base import Strategy
from strategies.registry import register_strategy

_VALID_BETA_METHODS = {"ols", "fixed", "kalman"}


@register_strategy("pair_trading")
class PairTradingStrategy(Strategy):
    """配对交易策略（基于价差 z-score）。"""

    name = "pair_trading"

    def __init__(
        self,
        pairs: list[tuple[str, str]],
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.5,
        lookback: int = 60,
        beta_method: str = "ols",
    ):
        self.pairs = pairs
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.lookback = lookback
        self.beta_method = beta_method

    def generate_signal(self, data, factors=None):
        return pair_trading_signal(
            data,
            pairs=self.pairs,
            entry_zscore=self.entry_zscore,
            exit_zscore=self.exit_zscore,
            lookback=self.lookback,
            beta_method=self.beta_method,
        )


def pair_trading_signal(
    df: pd.DataFrame,
    pairs: list[tuple[str, str]],
    entry_zscore: float = 2.0,
    exit_zscore: float = 0.5,
    lookback: int = 60,
    beta_method: str = "ols",
) -> pd.DataFrame:
    """生成配对交易信号。

    对每只股票输出一行，不在配对中的股票 signal=0, confidence=0.0。
    输出兼容现有管道（filter_tradable, enforce_t1, equal_weight 等）。

    重叠配对冲突解决：一只股票在同一时间只能属于一个活跃配对。
    按 pairs 列表顺序处理，先到先得——已持有信号的股票不会被后续配对覆盖。

    Parameters
    ----------
    df : DataFrame
        多只股票的 OHLCV 数据（date, code, close, ...）。
    pairs : list of (code_a, code_b)
        静态配对定义。每只股票只能出现在一个配对中（否则按列表顺序取第一个）。
    entry_zscore : float
        入场 z-score 阈值。
    exit_zscore : float
        出场 z-score 阈值。
    lookback : int
        z-score 滚动窗口。
    beta_method : str
        "ols" 使用滚动 OLS 估计 beta，"fixed" 使用 beta=1。

    Returns
    -------
    DataFrame
        包含 date, code, signal, confidence 列。
    """
    if df.empty or not pairs:
        return pd.DataFrame(columns=["date", "code", "signal", "confidence"])

    if beta_method not in _VALID_BETA_METHODS:
        raise ValueError(
            f"Unknown beta_method: {beta_method!r}. "
            f"Valid options: {_VALID_BETA_METHODS}"
        )

    # 去重：每个 (date, code) 只保留最后一行
    df = df.drop_duplicates(subset=["date", "code"], keep="last")
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # Pivot 到宽格式，每列一只股票的收盘价
    close_wide = df.pivot_table(index="date", columns="code", values="close")
    close_wide = close_wide.sort_index()

    # 初始化信号矩阵
    idx = close_wide.index
    cols = close_wide.columns
    signal_matrix = pd.DataFrame(0, index=idx, columns=cols, dtype=int)
    confidence_matrix = pd.DataFrame(0.0, index=idx, columns=cols)

    all_codes = set(close_wide.columns)
    # 跟踪已分配配对的股票，解决重叠配对冲突
    claimed_stocks: set[str] = set()

    for code_a, code_b in pairs:
        if code_a not in all_codes or code_b not in all_codes:
            continue

        # 重叠配对冲突：如果任一股票已被其他配对占用，跳过
        if code_a in claimed_stocks or code_b in claimed_stocks:
            continue

        claimed_stocks.add(code_a)
        claimed_stocks.add(code_b)

        prices_a = close_wide[code_a].dropna()
        prices_b = close_wide[code_b].dropna()

        # 对齐日期
        common_dates = prices_a.index.intersection(prices_b.index)
        if len(common_dates) < lookback + 1:
            continue

        pa = prices_a.loc[common_dates].values
        pb = prices_b.loc[common_dates].values

        log_a = np.log(pa)
        log_b = np.log(pb)

        # 预计算 Kalman beta（整个序列一次估计）
        if beta_method == "kalman":
            all_betas = get_factor("kalman_filter_hedge_ratio")(log_a, log_b)

        # 滚动计算 z-score
        zscores = np.full(len(common_dates), np.nan)

        for i in range(lookback, len(common_dates)):
            window_a = log_a[i - lookback : i + 1]
            window_b = log_b[i - lookback : i + 1]

            if beta_method == "ols":
                x = np.column_stack([window_b, np.ones(lookback + 1)])
                coeffs, _, _, _ = np.linalg.lstsq(x, window_a, rcond=None)
                beta = coeffs[0]
            elif beta_method == "kalman":
                beta = all_betas[i]
            else:
                beta = 1.0

            spread = window_a - beta * window_b
            mean_s = spread.mean()
            std_s = spread.std()

            if std_s > 1e-10:
                zscores[i] = (spread[-1] - mean_s) / std_s
            else:
                zscores[i] = 0.0

        # 生成信号（带迟滞）
        pair_signals = np.zeros(len(common_dates), dtype=int)
        pair_confidence = np.zeros(len(common_dates))
        current_pos = 0  # 0=空仓, 1=多A空B, -1=空A多B

        for i in range(len(common_dates)):
            z = zscores[i]
            if np.isnan(z):
                continue

            if current_pos == 0:
                # 空仓：寻找入场信号
                if z < -entry_zscore:
                    current_pos = 1  # long A, short B
                elif z > entry_zscore:
                    current_pos = -1  # short A, long B
            else:
                # 持仓：寻找出场信号
                if abs(z) < exit_zscore:
                    current_pos = 0

            if current_pos == 1:
                pair_signals[i] = 1  # A 买
                pair_confidence[i] = min(abs(z) / entry_zscore, 1.0)
            elif current_pos == -1:
                pair_signals[i] = -1  # A 卖
                pair_confidence[i] = min(abs(z) / entry_zscore, 1.0)

        # 写入信号矩阵
        for i, date in enumerate(common_dates):
            sig = pair_signals[i]
            conf = pair_confidence[i]
            if sig != 0:
                # A 腿
                if conf > confidence_matrix.loc[date, code_a]:
                    signal_matrix.loc[date, code_a] = sig
                    confidence_matrix.loc[date, code_a] = conf
                # B 腿（方向相反）
                if conf > confidence_matrix.loc[date, code_b]:
                    signal_matrix.loc[date, code_b] = -sig
                    confidence_matrix.loc[date, code_b] = conf

    # 展开回长格式
    result = df[["date", "code"]].copy()
    result["signal"] = 0
    result["confidence"] = 0.0

    for code in all_codes:
        if code in signal_matrix.columns:
            mask = result["code"] == code
            code_signals = signal_matrix[code].reindex(result.loc[mask, "date"].values)
            code_conf = confidence_matrix[code].reindex(result.loc[mask, "date"].values)
            result.loc[mask, "signal"] = code_signals.values
            result.loc[mask, "confidence"] = code_conf.values

    return result[["date", "code", "signal", "confidence"]]
