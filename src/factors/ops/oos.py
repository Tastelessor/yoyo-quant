"""因子 OOS 验证（Phase B）：walk-forward 窗口 + 选因子 + bootstrap 零分布。

纯函数、无状态，对齐 ``factors.ops.evaluation`` 的契约风格。不 import
``backtest.walk_forward``（避免回测链耦合）；窗口语义与其一致：
train 紧贴 test、滑窗步长 = test_months。
"""
from __future__ import annotations

import pandas as pd


def generate_oos_windows(
    dates: pd.DatetimeIndex | pd.Series,
    *,
    train_months: int = 12,
    test_months: int = 1,
) -> list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """生成 walk-forward 的 (train, test) 交易日窗口对。

    Parameters
    ----------
    dates : DatetimeIndex | Series
        全部可用交易日，升序（内部会去重排序）。
    train_months : int
        train 期长度（日历月）。
    test_months : int
        test 期长度（日历月）；滑窗步长 = test_months（窗口不重叠、连续推进）。

    Returns
    -------
    list of (train_idx, test_idx)
        每期返回两个实际交易日 DatetimeIndex（升序）。train 与 test 严格
        不相交且 train 紧贴 test；test 终点超出数据末日的期不产生。
    """
    if not isinstance(train_months, int) or train_months < 1:
        raise ValueError(f"train_months 必须为正整数，收到 {train_months!r}")
    if not isinstance(test_months, int) or test_months < 1:
        raise ValueError(f"test_months 必须为正整数，收到 {test_months!r}")
    dates = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(dates))))
    if len(dates) == 0:
        return []

    windows: list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]] = []
    cur = dates[0]
    while True:
        train_end_cal = cur + pd.DateOffset(months=train_months)
        test_start_cal = train_end_cal + pd.Timedelta(days=1)
        test_end_cal = test_start_cal + pd.DateOffset(months=test_months)
        if test_end_cal > dates[-1]:
            break
        train = dates[(dates >= cur) & (dates <= train_end_cal)]
        test = dates[(dates >= test_start_cal) & (dates <= test_end_cal)]
        if len(train) == 0 or len(test) == 0:
            cur = cur + pd.DateOffset(months=test_months)
            continue
        windows.append((train, test))
        cur = cur + pd.DateOffset(months=test_months)
    return windows
