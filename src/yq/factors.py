"""yq factor 子命令：注册表查询、单因子计算、IC/IR 评估。"""

import inspect
import json
from pathlib import Path

import pandas as pd
import typer

from analysis.factor_clean import run_phase_a
from analysis.factor_monitor import (
    DEFAULT_OUTPUT_DIR,
    diff_states,
    load_state,
    run_monitor,
)
from config.loader import load_factor_clean_config
from data.storage import load_parquet, save_parquet
from factors.ops.evaluation import DEFAULT_WINDOWS, evaluate_factors
from factors.registry import get_spec, list_factors, run_factor
from yq.monitor import build_status_table, render_changes
from yq.output import _records, render_dataframe

factor_app = typer.Typer(
    name="factor",
    help="因子注册表查询、计算与 IC/IR 评估",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _coerce_value(raw: str) -> int | float | bool | str:
    """把 --param k=v 的字符串值转成 int / float / bool / str。"""
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_params(param: list[str] | None) -> dict:
    """解析重复的 --param k=v。"""
    params: dict = {}
    for item in param or []:
        if "=" not in item:
            raise ValueError(f"--param 需为 k=v 格式，收到: {item!r}")
        k, v = item.split("=", 1)
        params[k] = _coerce_value(v)
    return params


def _doc_first_line(func) -> str:
    """取函数 docstring 首行（去掉装饰/空行）作为因子介绍。"""
    doc = inspect.getdoc(func) or ""
    for line in doc.splitlines():
        if line.strip():
            return line.strip()
    return ""


@factor_app.command("list")
def factor_list(
    tag: str | None = typer.Option(None, "--tag", help="按 tag 过滤，如 momentum"),
    kind: str | None = typer.Option(None, "--kind", help="按 kind 过滤：single / pair"),
    verbose: bool = typer.Option(
        False, "--verbose", help="附带因子介绍（docstring 首行）"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """列出注册表全部因子（名称/kind/tags/默认参数/介绍）。"""
    names = list_factors(tag=tag, kind=kind)
    rows = []
    for name in names:
        spec = get_spec(name)
        row = {
            "name": name,
            "kind": spec.kind,
            "tags": ", ".join(spec.tags) if spec.tags else "",
            "params": str(spec.params) if spec.params else "",
        }
        if verbose:
            row["description"] = _doc_first_line(spec.func)
        rows.append(row)
    verbose_cols = ["name", "kind", "tags", "params", "description"]
    columns = verbose_cols if verbose else ["name", "kind", "tags", "params"]
    df = pd.DataFrame(rows, columns=columns)
    typer.echo(render_dataframe(df, as_json=json_out))


@factor_app.command("run")
def factor_run(
    name: str = typer.Argument(..., help="已注册的 single 因子名"),
    input: Path = typer.Option(
        ..., "--input", "-i", help="行情 parquet 路径（需含 date/code/close 等列）"
    ),
    param: list[str] | None = typer.Option(
        None, "--param", help="因子参数 k=v，可重复，如 --param window=20"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="结果写为 parquet（date/code/因子列）"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用磁盘缓存"),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="缓存目录（默认 FACTOR_CACHE_DIR 或 data/factors/）"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """计算单个因子，结果与输入逐行对齐。"""
    try:
        df = load_parquet(input)
        params = _parse_params(param)
        series = run_factor(
            name,
            df,
            cache_dir=cache_dir,
            use_cache=not no_cache,
            **params,
        )
        result = pd.concat(
            [
                df[["date", "code"]].reset_index(drop=True),
                series.reset_index(drop=True),
            ],
            axis=1,
        )
        if output is not None:
            save_parquet(result, output)
            if json_out:
                typer.echo(json.dumps({"output": str(output), "rows": len(result)}))
            else:
                typer.echo(
                    f"已写入 {output}（{len(result)} 行 × {result.shape[1]} 列）"
                )
        else:
            typer.echo(render_dataframe(result, as_json=json_out))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@factor_app.command("evaluate")
def factor_evaluate(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="因子宽表 parquet（date/code/因子列；不传 --price 时需含 close）",
    ),
    factor: list[str] = typer.Option(
        ..., "--factor", "-f", help="要评估的因子列名，可重复"
    ),
    price: Path | None = typer.Option(
        None, "--price", help="行情 parquet（date/code/close），缺省用输入表 close"
    ),
    window: list[int] | None = typer.Option(
        None, "--window", help="前向收益窗口（交易日数），可重复，默认 1/5/20"
    ),
    method: str = typer.Option(
        "spearman", "--method", help="IC 方法：spearman / pearson / kendall"
    ),
    min_obs: int = typer.Option(5, "--min-obs", help="每日截面 IC 最少样本数"),
    quantiles: int = typer.Option(5, "--quantiles", help="分层数量"),
    rebalance_days: int | None = typer.Option(
        None, "--rebalance-days", help="分层组合调仓间隔（默认每日）"
    ),
    exclude_untradable: bool = typer.Option(
        False, "--exclude-untradable", help="IC 与分层剔除涨跌停/停牌日"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """批量评估因子：IC 均值/IR/正相关占比 + 多空分层收益。"""
    try:
        factor_df = load_parquet(input)
        price_df = load_parquet(price) if price is not None else None
        windows = tuple(window) if window else DEFAULT_WINDOWS
        summary = evaluate_factors(
            factor_df,
            factor,
            price_df,
            windows=windows,
            method=method,
            min_obs=min_obs,
            n_quantiles=quantiles,
            rebalance_days=rebalance_days,
            exclude_untradable=exclude_untradable,
        )
        if json_out:
            payload = {
                "summary": _records(summary),
                "config": {
                    "windows": list(windows),
                    "method": method,
                    "min_obs": min_obs,
                    "n_quantiles": quantiles,
                    "rebalance_days": rebalance_days,
                    "exclude_untradable": exclude_untradable,
                },
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(render_dataframe(summary, as_json=False))
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@factor_app.command("monitor")
def factor_monitor(
    data: Path = typer.Option(
        ...,
        "--data",
        help="行情 parquet（date/code/close，可选 limit_up/limit_down/is_suspended）",
    ),
    factor: list[str] | None = typer.Option(
        None, "--factor", "-f", help="因子名，可重复；缺省动态发现全部 single 因子"
    ),
    windows: str = typer.Option(
        "5", "--windows", help="forward 收益窗口（交易日数），逗号分隔，如 1,5,20"
    ),
    window: int = typer.Option(
        60, "--window", help="滚动 IC/IR/t 统计窗口（交易日数）"
    ),
    min_sustain: int = typer.Option(
        20, "--min-sustain", help="状态切换最短持续日数（防抖）"
    ),
    min_obs: int = typer.Option(5, "--min-obs", help="单日截面 IC 最少样本数"),
    t_active: float = typer.Option(2.0, "--t-active", help="活跃阈值 |t|"),
    t_decay: float = typer.Option(1.0, "--t-decay", help="失效阈值 |t|"),
    ir_active_line: float = typer.Option(
        0.7, "--ir-active-line", help="滚动 IR 活跃参考线（绘图用）"
    ),
    ir_dead_line: float = typer.Option(
        0.3, "--ir-dead-line", help="滚动 IR 失效参考线（绘图用）"
    ),
    full: bool = typer.Option(False, "--full", help="全量重算（忽略增量历史）"),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用因子磁盘缓存"),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR, "--output-dir", help="state/changes 输出目录"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """因子生命周期监控：滚动 IC/IR/t → active/decaying/dead 状态 → 持久化。

    首次运行全量计算；之后默认只重算尾部（见 state.parquet 的 last_date）。
    输出状态摘要表（每 factor×fwd_window 一行，dead 置顶）与本次状态切换。
    """
    try:
        price_df = load_parquet(data)
        fwd_windows = tuple(int(x) for x in windows.split(",") if x.strip())
        if not fwd_windows:
            raise ValueError("--windows 需为逗号分隔的正整数")
        old_state = load_state(Path(output_dir) / "state.parquet")
        state, skipped = run_monitor(
            price_df,
            factor_names=factor,
            fwd_windows=fwd_windows,
            window=window,
            min_sustain=min_sustain,
            min_obs=min_obs,
            t_active=t_active,
            t_decay=t_decay,
            exclude_untradable=True,
            output_dir=output_dir,
            full=full,
            use_cache=not no_cache,
        )
        if skipped:
            typer.echo(
                f"跳过 {len(skipped)} 个因子（缺输入列，无法用行情计算）: "
                f"{', '.join(skipped)}",
                err=True,
            )
        changes = diff_states(state, old_state)
        status = build_status_table(state)

        # ---- 绘图：health_heatmap + 每 (factor, fwd_window) 一张 lifecycle ----
        # CLI 只保存图不交互显示，统一 Agg 后端（须在 import pyplot 前设置）
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from analysis.plot import plot_factor_health_heatmap, plot_factor_lifecycle

        fig_dir = Path(output_dir) / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        fig_paths: list[str] = []
        if not state.empty:
            heat = plot_factor_health_heatmap(state)
            heat_path = fig_dir / "health_heatmap.png"
            heat.savefig(heat_path, dpi=100, bbox_inches="tight")
            plt.close(heat)
            fig_paths.append(str(heat_path))
            for (fname, fw), sub in state.groupby(["factor", "fwd_window"]):
                fig = plot_factor_lifecycle(
                    sub,
                    t_active=t_active,
                    t_decay=t_decay,
                    ir_active_line=ir_active_line,
                    ir_dead_line=ir_dead_line,
                    title=f"{fname} fwd={fw}",
                )
                life_path = fig_dir / f"lifecycle_{fname}_fwd{fw}.png"
                fig.savefig(life_path, dpi=100, bbox_inches="tight")
                plt.close(fig)
                fig_paths.append(str(life_path))
        config = {
            "windows": list(fwd_windows),
            "window": window,
            "min_sustain": min_sustain,
            "min_obs": min_obs,
            "t_active": t_active,
            "t_decay": t_decay,
            "ir_active_line": ir_active_line,
            "ir_dead_line": ir_dead_line,
            "full": full,
            "exclude_untradable": True,
        }
        if json_out:
            payload = {
                "status": _records(status),
                "changes": _records(changes),
                "config": config,
                "figures": fig_paths,
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(render_dataframe(status, as_json=False))
            typer.echo("")
            typer.echo(render_changes(changes))
            typer.echo(f"state 已写入 {Path(output_dir) / 'state.parquet'}")
            if fig_paths:
                typer.echo(f"图已保存: {', '.join(fig_paths)}")
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@factor_app.command("clean-a")
def factor_clean_a(
    state: Path = typer.Option(..., "--state", help="monitor 输出的 state.parquet"),
    data: Path = typer.Option(..., "--data", help="全市场行情 parquet"),
    config: Path | None = typer.Option(None, "--config", help="factor_clean.yaml"),
    window: int | None = typer.Option(None, "--window", help="相关滚动窗口（交易日）"),
    threshold: float | None = typer.Option(
        None, "--threshold", help="冗余判定阈值 |ρ|"
    ),
    linkage: str | None = typer.Option(None, "--linkage", help="层次聚类连接方式"),
    by: str | None = typer.Option(None, "--by", help="代表标准：t_stat|ir|combined"),
    fwd_window: int | None = typer.Option(
        None, "--fwd-window", help="state 的 forward 窗口"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用因子磁盘缓存"),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="输出目录"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """Phase A：因子相关性去冗余（state + ohlcv → 代表因子清单）。"""
    # 优先级：CLI 显式参数 > config 文件 > 内置默认（FACTOR_CLEAN_DEFAULTS）
    cfg = load_factor_clean_config(config) if config is not None else {}
    window = window if window is not None else int(cfg.get("corr_window", 60))
    threshold = (
        threshold if threshold is not None else float(cfg.get("corr_threshold", 0.7))
    )
    linkage = (
        linkage if linkage is not None else str(cfg.get("cluster_linkage", "ward"))
    )
    by = by if by is not None else str(cfg.get("representative_by", "t_stat"))
    fwd_window = fwd_window if fwd_window is not None else int(cfg.get("fwd_window", 5))
    out = run_phase_a(
        state_path=state,
        ohlcv_path=data,
        corr_window=window,
        corr_threshold=threshold,
        cluster_linkage=linkage,
        representative_by=by,
        fwd_window=fwd_window,
        use_cache=not no_cache,
        output_dir=output_dir,
    )
    reps = out["representatives"]
    summary = [
        {
            "cluster_id": int(r["cluster_id"]),
            "representative": r["representative"],
            "members": list(r["members"]),
        }
        for r in reps.to_dict("records")
    ]
    if json_out:
        import json as _json

        typer.echo(
            _json.dumps(
                {
                    "as_of": str(out["as_of"].date()),
                    "factors": out["factors"],
                    "skipped": out["skipped"],
                    "clusters": summary,
                    "outputs": str(output_dir) if output_dir else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo(
        f"as_of: {out['as_of'].date()}  候选因子: {len(out['factors'])}  "
        f"簇数: {len(reps)}"
    )
    for r in summary:
        typer.echo(
            f"  簇 {r['cluster_id']}: 代表因子 {r['representative']}"
            f"（成员 {r['members']}）"
        )
    if out["skipped"]:
        typer.echo(f"跳过（缺列）: {out['skipped']}", err=True)
    if output_dir is not None:
        typer.echo(f"输出: {output_dir}")
