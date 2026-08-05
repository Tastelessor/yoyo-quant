"""多因子选股策略。

对每只股票计算多个因子得分，按综合排名轮动持仓。
- 动量因子：过去 N 日收益率（高=好）
- 反转因子：RSI 超卖程度（低 RSI=买入机会）
- 波动率因子：低波动率溢价（低 HV=好）
- 成交量因子：放量确认（高 volume_ratio=好）

在每个再平衡日，买入综合得分最高的 top_n 只，卖出 bottom_n 只。
"""

from __future__ import annotations

import pandas as pd

from factors.registry import run_factor
from strategies.base import Strategy
from strategies.registry import register_strategy

DEFAULT_WEIGHTS = {
    "momentum": 1.0,
    "rsi": 1.0,
    "volatility": 1.0,
    "volume": 0.5,
}


@register_strategy("multifactor")
class MultifactorStrategy(Strategy):
    """Multi-factor scoring and rotation strategy."""

    name = "multifactor"

    def __init__(
        self,
        momentum_window: int = 20,
        rsi_window: int = 14,
        hv_window: int = 20,
        vol_window: int = 20,
        rebalance: int = 20,
        top_n: int = 5,
        bottom_n: int = 3,
        weights: dict | None = None,
    ):
        self.momentum_window = momentum_window
        self.rsi_window = rsi_window
        self.hv_window = hv_window
        self.vol_window = vol_window
        self.rebalance = rebalance
        self.top_n = top_n
        self.bottom_n = bottom_n
        self.weights = weights or DEFAULT_WEIGHTS

    def generate_signal(self, data, factors=None):
        return multifactor_signal(
            data,
            momentum_window=self.momentum_window,
            rsi_window=self.rsi_window,
            hv_window=self.hv_window,
            vol_window=self.vol_window,
            rebalance=self.rebalance,
            top_n=self.top_n,
            bottom_n=self.bottom_n,
            weights=self.weights,
        )


def _rank_normalize(s: pd.Series) -> pd.Series:
    """将 Series 按截面排名归一化到 [0, 1]。"""
    ranked = s.rank(pct=True)
    return ranked


def multifactor_signal(
    df: pd.DataFrame,
    momentum_window: int = 20,
    rsi_window: int = 14,
    hv_window: int = 20,
    vol_window: int = 20,
    rebalance: int = 20,
    top_n: int = 5,
    bottom_n: int = 3,
    weights: dict | None = None,
) -> pd.DataFrame:
    """多因子选股信号。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close, volume 列。
    momentum_window : int
        动量因子窗口。
    rsi_window : int
        RSI 窗口。
    hv_window : int
        波动率因子窗口。
    vol_window : int
        成交量比率窗口。
    rebalance : int
        再平衡周期（交易日）。
    top_n : int
        买入排名前 N 的股票。
    bottom_n : int
        卖出排名后 N 的股票。
    weights : dict | None
        因子权重，键为 factor 名，值为权重。

    Returns
    -------
    DataFrame
        包含 date, code, signal, confidence 列。
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())

    # 计算因子（全量计算，每行一个值）
    # 动量：N 日收益率
    momentum = df.groupby("code")["close"].transform(
        lambda s: s.pct_change(momentum_window)
    )

    # RSI：归一化到 0-1（RSI/100）
    rsi_raw = run_factor("calc_rsi", df, window=rsi_window)
    rsi_score = (100 - rsi_raw) / 100  # 反转因子：RSI 越低得分越高

    # 波动率：取反（低波动 = 高得分）
    hv_raw = run_factor("calc_hv", df, window=hv_window)
    hv_score = -hv_raw  # 取反后排名时低波动得高分

    # 成交量比率
    vol_raw = run_factor("calc_volume_ratio", df, window=vol_window)
    vol_score = vol_raw

    # 组合成因子 DataFrame
    factors_df = pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "close": df["close"],
            "momentum": momentum,
            "rsi": rsi_score,
            "volatility": hv_score,
            "volume": vol_score,
        }
    )

    # 初始化信号
    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)

    # 在每个再平衡日打分
    min_window = max(momentum_window, rsi_window, hv_window, vol_window) + 1
    rebalance_dates = [
        all_dates[i] for i in range(min_window, len(all_dates), rebalance)
    ]

    prev_holdings: set[str] = set()

    for rb_date in rebalance_dates:
        # 取当天所有股票的因子值
        day_mask = factors_df["date"] == rb_date
        day_data = factors_df[day_mask].copy()

        if len(day_data) < 2:
            continue

        # 截面排名归一化
        factor_names = [
            f for f in ["momentum", "rsi", "volatility", "volume"] if f in weights
        ]
        day_data["score"] = 0.0
        total_weight = 0.0
        for f in factor_names:
            w = weights[f]
            day_data["score"] += _rank_normalize(day_data[f]) * w
            total_weight += w

        if total_weight > 0:
            day_data["score"] /= total_weight

        # 排序
        day_data = day_data.sort_values("score", ascending=False)

        # 选出 top_n 和 bottom_n
        buy_codes = set(day_data.head(top_n)["code"].tolist()) if top_n > 0 else set()
        sell_codes = (
            set(day_data.tail(bottom_n)["code"].tolist()) if bottom_n > 0 else set()
        )

        # 生成信号：在再平衡日及之后直到下一个再平衡日
        rb_idx = all_dates.index(rb_date)
        next_rb_idx = min(rb_idx + rebalance, len(all_dates))
        holding_dates = all_dates[rb_idx:next_rb_idx]

        for h_date in holding_dates:
            h_mask = df["date"] == h_date
            for code in buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = 1
                    score_val = day_data[day_data["code"] == code]["score"].values
                    confidence.iloc[idx] = (
                        float(score_val[0]) if len(score_val) > 0 else 0.5
                    )

            for code in sell_codes - buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = -1
                    confidence.iloc[idx] = 0.5

        # 追踪持仓变化：退出持仓的股票卖出
        exited = prev_holdings - buy_codes
        for code in exited:
            mask = (df["date"] == rb_date) & (df["code"] == code)
            idx = df.index[mask]
            if len(idx) > 0:
                signal.iloc[idx] = -1
                confidence.iloc[idx] = 0.5

        prev_holdings = buy_codes

    # 窗口不足的行置零
    first_valid_date = (
        all_dates[min_window] if min_window < len(all_dates) else all_dates[-1]
    )
    early_mask = df["date"] < first_valid_date
    signal[early_mask] = 0
    confidence[early_mask] = 0.0

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
