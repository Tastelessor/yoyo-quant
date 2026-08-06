import numpy as np
import pandas as pd
import pytest

from factors.ops.correlation import cluster_redundant, compute_corr_matrix


def _make_factor_df(seed=0, n_days=100, n_stocks=40):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    codes = [f"{600000 + i}" for i in range(n_stocks)]
    s = rng.normal(size=n_stocks)   # F1/F2 共享的股票特质分
    t = rng.normal(size=n_stocks)   # F3 独立特质分
    rows = []
    for d in dates:
        for i, c in enumerate(codes):
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "f1": s[i] + rng.normal(scale=0.05),
                    "f2": s[i] + rng.normal(scale=0.05),
                    "f3": t[i] + rng.normal(scale=0.05),
                }
            )
    return pd.DataFrame(rows)


def test_corr_matrix_high_corr_pair():
    df = _make_factor_df()
    mat = compute_corr_matrix(df, ["f1", "f2", "f3"])
    assert mat.loc["f1", "f2"] > 0.9   # 同源 → 每天排序几乎一致
    assert abs(mat.loc["f1", "f3"]) < 0.3  # 独立 → 接近 0


def test_corr_matrix_symmetric_diagonal():
    df = _make_factor_df()
    mat = compute_corr_matrix(df, ["f1", "f2", "f3"])
    assert list(mat.index) == ["f1", "f2", "f3"]
    assert list(mat.columns) == ["f1", "f2", "f3"]
    assert mat.loc["f1", "f2"] == pytest.approx(mat.loc["f2", "f1"])
    assert (np.diag(mat.to_numpy()) == 1.0).all()
    assert mat.values.dtype == np.float64


def test_corr_matrix_window_truncation():
    # 前 80 天 f1 与 f2 同向，后 20 天反向 → 短窗口看到负相关
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2025-06-02", periods=100)
    codes = [f"{600000 + i}" for i in range(20)]
    rows = []
    for i, d in enumerate(dates):
        for j, c in enumerate(codes):
            v = rng.normal(size=1)[0]
            sign = 1.0 if i < 80 else -1.0
            f2 = sign * v + rng.normal(scale=0.05)
            rows.append({"date": d, "code": c, "f1": v, "f2": f2})
    df = pd.DataFrame(rows)
    short = compute_corr_matrix(df, ["f1", "f2"], window=20)
    full = compute_corr_matrix(df, ["f1", "f2"], window=100)
    assert short.loc["f1", "f2"] < -0.5
    assert full.loc["f1", "f2"] > 0.0


def test_corr_matrix_insufficient_obs_nan():
    df = _make_factor_df(n_stocks=5)  # 每日截面仅 5 个样本
    mat = compute_corr_matrix(df, ["f1", "f2"], min_obs=50)
    assert np.isnan(mat.loc["f1", "f2"])


def test_corr_matrix_missing_column_raises():
    df = _make_factor_df()
    with pytest.raises(ValueError, match="f4"):
        compute_corr_matrix(df, ["f1", "f4"])


def test_corr_matrix_bad_args_raise():
    df = _make_factor_df()
    with pytest.raises(ValueError, match="agg"):
        compute_corr_matrix(df, ["f1", "f2"], agg="max")
    with pytest.raises(ValueError, match="window"):
        compute_corr_matrix(df, ["f1", "f2"], window=0)


def _corr_of(pairs, factors=("a", "b", "c")):
    # 由 (f1, f2, rho) 列表构造对称矩阵，未给的对为 0
    mat = pd.DataFrame(np.zeros((3, 3)), index=list(factors), columns=list(factors))
    for f1, f2, r in pairs:
        mat.loc[f1, f2] = mat.loc[f2, f1] = r
    np.fill_diagonal(mat.to_numpy(), 1.0)
    return mat


def test_cluster_high_corr_grouped():
    corr = _corr_of([("a", "b", 0.95), ("a", "c", 0.1), ("b", "c", 0.05)])
    out = cluster_redundant(corr, threshold=0.7)
    assert out.loc[out["factor"] == "a", "cluster_id"].iloc[0] == out.loc[
        out["factor"] == "b", "cluster_id"
    ].iloc[0]
    assert out.loc[out["factor"] == "c", "cluster_id"].iloc[0] != out.loc[
        out["factor"] == "a", "cluster_id"
    ].iloc[0]


def test_cluster_all_independent():
    corr = pd.DataFrame(np.eye(3), index=["a", "b", "c"], columns=["a", "b", "c"])
    out = cluster_redundant(corr, threshold=0.7)
    assert out["cluster_id"].nunique() == 3


def test_cluster_threshold_monotonic():
    # 仅 a/b 两因子：0.95 > 0.7 → 一簇；0.95 < 0.98 → 两簇
    corr = pd.DataFrame(
        [[1.0, 0.95], [0.95, 1.0]], index=["a", "b"], columns=["a", "b"]
    )
    loose = cluster_redundant(corr, threshold=0.7)
    strict = cluster_redundant(corr, threshold=0.98)
    assert loose["cluster_id"].nunique() == 1
    assert strict["cluster_id"].nunique() == 2


def test_cluster_single_factor():
    corr = pd.DataFrame([[1.0]], index=["a"], columns=["a"])
    out = cluster_redundant(corr, threshold=0.7)
    assert out.to_dict("records") == [{"factor": "a", "cluster_id": 0}]


def test_cluster_nan_safe():
    corr = _corr_of([("a", "b", 0.95)])
    corr.loc["a", "c"] = corr.loc["c", "a"] = np.nan
    out = cluster_redundant(corr, threshold=0.7)
    assert len(out) == 3


def test_cluster_invalid_threshold():
    corr = _corr_of([("a", "b", 0.95)])
    with pytest.raises(ValueError, match="threshold"):
        cluster_redundant(corr, threshold=1.5)
