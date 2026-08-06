"""Phase B 编排：walk-forward OOS 验证（analysis 层）。

只读 monitor 的 state 长表 + 全市场 ohlcv；每期在 train 段选因子
（去冗余 + bootstrap 零分布过滤 + top-K），在 test 段重算 IC 验证。
不重算 monitor 的滚动统计。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.factor_monitor import LOOKBACK_MAX, STATE_COLS
from factors.ops.correlation import (
    cluster_redundant,
    compute_corr_matrix,
    select_representative,
)
from factors.ops.evaluation import compute_forward_returns, compute_ic
from factors.ops.oos import (
    bootstrap_t_distribution,
    compute_test_period_stats,
    generate_oos_windows,
    select_top_factors,
)
from factors.registry import run_factor

ACTIVE_STATES = ("active", "decaying")

PERIOD_COLS = [
    "period_idx",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "factor",
    "cluster_id",
    "train_t",
    "null_95",
    "selected",
    "test_ic_mean",
    "test_ic_t",
    "test_ic_n",
    "test_sig",
    "win",
]


def _load_state(state_path: Path) -> pd.DataFrame:
    path = Path(state_path)
    if not path.exists():
        raise FileNotFoundError(f"state 文件不存在: {path}")
    df = pd.read_parquet(path)
    if not set(STATE_COLS).issubset(df.columns):
        raise ValueError(f"state.parquet 缺少列，需要 {STATE_COLS}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _period_rec(pi: int, train_idx, test_idx) -> dict:
    return {
        "period_idx": pi,
        "train_start": train_idx[0],
        "train_end": train_idx[-1],
        "test_start": test_idx[0],
        "test_end": test_idx[-1],
    }


def run_phase_b(
    *,
    state_path: Path,
    ohlcv_path: Path,
    train_months: int = 12,
    test_months: int = 1,
    top_k: int = 5,
    bootstrap_iters: int = 200,
    t_window: int = 60,
    corr_window: int = 60,
    corr_threshold: float = 0.7,
    cluster_linkage: str = "ward",
    representative_by: str = "t_stat",
    fwd_window: int = 5,
    exclude_untradable: bool = True,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    output_dir: Path | None = None,
    seed: int = 42,
) -> dict:
    """Phase B 编排：train 选因子 → test 期 OOS 验证。

    Parameters 对齐 run_phase_a 风格；``t_window`` 是 bootstrap 零分布的
    尾部窗口（与 monitor 滚动 t 口径一致），``corr_window`` 是去冗余相关窗口。

    Returns
    -------
    dict
        periods（PERIOD_COLS 长表）/ summary。output_dir 给定时写
        oos_results.parquet + oos_summary.json + oos_winrate.png + oos_bootstrap.png。
    """
    state = _load_state(state_path)
    for key, val in (
        ("train_months", train_months),
        ("test_months", test_months),
        ("top_k", top_k),
        ("bootstrap_iters", bootstrap_iters),
        ("t_window", t_window),
    ):
        if not isinstance(val, int) or val < 1:
            raise ValueError(f"{key} 必须为正整数，收到 {val!r}")
    if not 0.0 < corr_threshold < 1.0:
        raise ValueError(f"corr_threshold 必须在 (0,1) 内，收到 {corr_threshold!r}")
    price = pd.read_parquet(ohlcv_path)
    price["date"] = pd.to_datetime(price["date"])
    dates = pd.DatetimeIndex(sorted(price["date"].unique()))
    windows = generate_oos_windows(
        dates, train_months=train_months, test_months=test_months
    )
    if not windows:
        raise ValueError("数据长度不足以构成任何 train/test 窗口")
    if len(windows[0][1]) <= fwd_window + 5:
        raise ValueError(
            f"test 期过短（{len(windows[0][1])} 天），不足以支撑 "
            f"fwd_window={fwd_window} 的 OOS 验证"
        )

    rows: list[dict] = []
    period_wr: list[dict] = []
    null95s: list[float] = []
    pos = {d: i for i, d in enumerate(dates)}

    for pi, (train_idx, test_idx) in enumerate(windows):
        rec = _period_rec(pi, train_idx, test_idx)
        as_of = train_idx[-1]
        cand_mask = (
            (state["date"] == as_of)
            & (state["state"].isin(ACTIVE_STATES))
            & (state["fwd_window"] == fwd_window)
        )
        candidates = sorted(state.loc[cand_mask, "factor"].unique().tolist())
        if not candidates:
            period_wr.append({**rec, "selected": 0, "win_rate": np.nan})
            continue

        # 因子值：只切该期需要的行段（train 前留 lookback，test 后留 fwd 缓冲）
        start_pos = max(0, pos[train_idx[0]] - LOOKBACK_MAX)
        end_pos = min(len(dates) - 1, pos[test_idx[-1]] + fwd_window)
        seg = price[price["date"].isin(dates[start_pos : end_pos + 1])]

        values: dict[str, pd.Series] = {}
        for f in candidates:
            try:
                values[f] = run_factor(f, seg, cache_dir=cache_dir, use_cache=use_cache)
            except KeyError:
                continue  # 缺列：该因子本期待用，跳过
        keep = [f for f in candidates if f in values]
        if not keep:
            period_wr.append({**rec, "selected": 0, "win_rate": np.nan})
            continue
        factor_df = seg.assign(**{f: values[f].to_numpy() for f in keep})

        # train 期末端统计（state 直接取，不重算）
        latest = state[(state["date"] == as_of) & (state["fwd_window"] == fwd_window)]
        train_stats = (
            latest[["factor", "t_stat", "rolling_ir"]]
            .drop_duplicates("factor")
            .rename(columns={"rolling_ir": "ir"})
        )
        train_t = dict(zip(train_stats["factor"], train_stats["t_stat"]))

        # 去冗余：train 末端 corr_window 天
        train_days = pd.DatetimeIndex(sorted(factor_df["date"].unique()))[-corr_window:]
        train_df = factor_df[factor_df["date"].isin(train_days)]
        if len(keep) > 1:
            corr = compute_corr_matrix(train_df, keep, window=corr_window)
            clusters = cluster_redundant(
                corr, threshold=corr_threshold, linkage_method=cluster_linkage
            )
            reps_df = select_representative(clusters, train_stats, by=representative_by)
            reps = reps_df["representative"].tolist()
            cluster_of = dict(zip(clusters["factor"], clusters["cluster_id"]))
        else:
            reps = list(keep)
            cluster_of = {keep[0]: 0}

        # bootstrap 零分布（路径②）：逐因子 AR(1) 残差打乱重建，不跨因子混合。
        # 每因子用自己的 IC 序列拟合 AR(1) → 残差打乱重建（均值归 0）→
        # 自身 |t| 的 95 分位作门槛。因子间门槛独立（IC 尺度/自相关不可比）。
        null_95_by_factor: dict[str, float] = {}
        ic_mask = (
            (state["date"] >= train_idx[0])
            & (state["date"] <= as_of)
            & (state["fwd_window"] == fwd_window)
            & (state["factor"].isin(candidates))
        )
        for f, ic in state.loc[ic_mask, ["factor", "ic"]].groupby("factor")["ic"]:
            if ic.dropna().size >= t_window:
                null_dist = bootstrap_t_distribution(
                    ic, bootstrap_iters, t_window, seed=seed
                )
                null_95_by_factor[f] = float(np.nanquantile(np.abs(null_dist), 0.95))
        null95s.extend(null_95_by_factor.values())

        # 入选：代表集 ∩ |t| > max(1, 该因子自身 null_95)，按 |t| 降序取 top_k
        pool = [
            f
            for f in reps
            if f in train_t
            and f in null_95_by_factor
            and np.abs(train_t[f]) > max(1.0, null_95_by_factor[f])
        ]
        pool.sort(key=lambda f: -abs(train_t[f]))
        selected = select_top_factors(
            pd.DataFrame({"factor": pool, "t_stat": [train_t[f] for f in pool]}),
            top_k,
        )

        # test 期验证：IC 只在 test 段重算（含 fwd 缓冲），不可交易日剔除
        test_df = factor_df[factor_df["date"].isin(test_idx)]
        fwd = compute_forward_returns(
            test_df, (fwd_window,), exclude_untradable=exclude_untradable
        )
        for f in selected:
            ic = compute_ic(test_df, f, fwd[fwd_window])
            st = compute_test_period_stats(ic)
            tt = float(train_t[f])
            if np.isnan(tt) or np.isnan(st["ic_t"]):
                win = False
            else:
                win = bool(
                    (tt > 0 and st["ic_t"] > 2.0) or (tt < 0 and st["ic_t"] < -2.0)
                )
            rows.append(
                {
                    **rec,
                    "factor": f,
                    "cluster_id": cluster_of.get(f, 0),
                    "train_t": tt,
                    "null_95": null_95_by_factor.get(f, np.nan),
                    "selected": True,
                    "test_ic_mean": st["ic_mean"],
                    "test_ic_t": st["ic_t"],
                    "test_ic_n": st["ic_n"],
                    "test_sig": st["sig"],
                    "win": win,
                }
            )
        period_wr.append(
            {
                **rec,
                "selected": len(selected),
                "win_rate": (
                    float(np.mean([r["win"] for r in rows if r["period_idx"] == pi]))
                    if selected
                    else np.nan
                ),
            }
        )

    periods = pd.DataFrame(rows, columns=PERIOD_COLS)
    n_sel = len(periods)
    summary = {
        "train_months": train_months,
        "test_months": test_months,
        "top_k": top_k,
        "bootstrap_iters": bootstrap_iters,
        "t_window": t_window,
        "periods_total": len(windows),
        "periods_with_selection": int(sum(p["selected"] > 0 for p in period_wr)),
        "periods_selected_total": int(sum(p["selected"] for p in period_wr)),
        "overall_win_rate": (float(periods["win"].mean()) if n_sel else np.nan),
        "overall_sig_rate": (float(periods["test_sig"].mean()) if n_sel else np.nan),
        "null_95_mean": float(np.mean(null95s)) if null95s else np.nan,
        "period_win_rates": period_wr,
    }

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        periods.to_parquet(out / "oos_results.parquet", index=False)
        (out / "oos_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        from analysis.plot import plot_bootstrap_null, plot_oos_winrate

        plot_oos_winrate(pd.DataFrame(period_wr)).savefig(
            out / "oos_winrate.png", dpi=110, bbox_inches="tight"
        )
        if len(periods) > 0:
            plot_bootstrap_null(
                periods["factor"].tolist(),
                periods["train_t"].abs().tolist(),
                periods["null_95"].tolist(),
            ).savefig(out / "oos_bootstrap.png", dpi=110, bbox_inches="tight")

    return {"periods": periods, "summary": summary}
