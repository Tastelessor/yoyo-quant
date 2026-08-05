"""yq factor 子命令：注册表查询、单因子计算、IC/IR 评估。"""

import inspect
import json
from pathlib import Path

import pandas as pd
import typer

from data.storage import load_parquet, save_parquet
from factors.evaluation import DEFAULT_WINDOWS, evaluate_factors
from factors.registry import get_spec, list_factors, run_factor
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
                typer.echo(f"已写入 {output}（{len(result)} 行 × {result.shape[1]} 列）")
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
