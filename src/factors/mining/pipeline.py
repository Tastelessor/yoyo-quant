"""factors/mining/pipeline.py — 因子挖掘评估编排（最小版）。

数据准备（ohlcv + daily_basic + moneyflow → 宽表）→ 因子值 →
全市场 + 分层 IC 验证 → 适用域判定。只读 parquet 产物，不 import data/ 与 analysis/。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from factors.ops.evaluation import compute_forward_returns, compute_ic_by_layer
from factors.ops.layering import compute_size_liquidity_layers
from factors.registry import run_factor

DEFAULT_MONEYFLOW_FACTORS = [
    "calc_moneyflow_net_ratio",
    "calc_moneyflow_streak",
    "calc_moneyflow_big_net_ratio",
]


def _domain_for(row: pd.Series, t_active: float, layer_t: float) -> str | list[str]:
    """适用域判定：全市场 t ≥ t_active → universal；否则列出显著层（Bonferroni）。"""
    if row["all_t_stat"] >= t_active:
        return "universal"
    sig = [c.replace("_t_stat", "") for c in row.index
           if c.endswith("_t_stat") and c != "all_t_stat"
           and pd.notna(row[c]) and row[c] >= layer_t]
    return sig if sig else "none"


def run_mining_screen(
    *,
    ohlcv_path: Path,
    basic_path: Path,
    moneyflow_path: Path,
    factors: list[str] | None = None,
    fwd_window: int = 5,
    min_obs: int = 5,
    min_days: int = 10,
    t_active: float = 2.0,
    layer_t: float = 2.81,
    output_dir: Path | None = None,
) -> dict:
    """分层验证评估编排：因子 → 全市场 + 9 层 IC → 适用域标签。

    Parameters
    ----------
    ohlcv_path : Path
        行情 parquet（date/code/close + 状态列，forward return 与可交易性用）。
    basic_path : Path
        daily_basic parquet（date/code/circ_mv/turnover_rate，层标签用）。
    moneyflow_path : Path
        moneyflow 长表 parquet（date/code + 资金流列，因子输入）。
    factors : list[str] | None
        待评估因子名；None → 默认资金流三因子。
    fwd_window : int
        forward return 窗口（交易日）。
    min_obs / min_days : int
        透传 compute_ic_by_layer。
    t_active : float
        全市场显著阈值（与 monitor 一致，默认 2.0）。
    layer_t : float
        层显著阈值（Bonferroni 校正 n=10、α=0.05、双侧、大样本近似 z≈2.81）。
    output_dir : Path | None
        给定时写 screen.parquet / layers.parquet / summary.json。

    Returns
    -------
    dict
        键：screen（index=因子，列 = all_mean_ic/all_t_stat/all_n_days +
        9 层 × {mean_ic,t_stat,n_days} + domain）、layers（层标签表）、summary。
    """
    ohlcv = pd.read_parquet(ohlcv_path)
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    basic = pd.read_parquet(basic_path)
    basic["date"] = pd.to_datetime(basic["date"])
    mf = pd.read_parquet(moneyflow_path)
    mf["date"] = pd.to_datetime(mf["date"])

    # 宽表：ohlcv + daily_basic + moneyflow（按 date/code 对齐）
    wide = ohlcv.merge(
        basic[["date", "code", "circ_mv", "turnover_rate"]],
        on=["date", "code"],
        how="left",
    )
    wide = wide.merge(mf, on=["date", "code"], how="left")

    layers = compute_size_liquidity_layers(basic)
    fwd = compute_forward_returns(ohlcv, [fwd_window])[fwd_window]

    factor_names = factors or DEFAULT_MONEYFLOW_FACTORS
    rows: dict[str, dict] = {}
    for f in factor_names:
        # run_factor 返回与 wide 行对齐的 Series；compute_ic_by_layer 需要
        # factor_df 含因子名列。用 to_numpy() 位置赋值（与 evaluation.py
        # 的 fwd 位置赋值一致），避免 assign 按索引对齐的隐式契约。
        factor_series = run_factor(f, wide)
        wide_with_factor = wide.copy()
        wide_with_factor[f] = factor_series.to_numpy()
        ic_table = compute_ic_by_layer(
            wide_with_factor,
            f, fwd, layers, min_obs=min_obs, min_days=min_days,
        )
        flat: dict = {}
        for layer_name in ic_table.index:
            prefix = "all" if layer_name == "all" else layer_name
            flat[f"{prefix}_mean_ic"] = ic_table.loc[layer_name, "mean_ic"]
            flat[f"{prefix}_t_stat"] = ic_table.loc[layer_name, "t_stat"]
            flat[f"{prefix}_n_days"] = ic_table.loc[layer_name, "n_days"]
        rows[f] = flat
    screen = pd.DataFrame.from_dict(rows, orient="index")
    screen["domain"] = screen.apply(
        lambda r: _domain_for(r, t_active, layer_t), axis=1
    )

    summary = {f: {"domain": screen.loc[f, "domain"]} for f in factor_names}

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        screen.to_parquet(out / "screen.parquet")
        layers.to_parquet(out / "layers.parquet", index=False)
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    return {"screen": screen, "layers": layers, "summary": summary}
