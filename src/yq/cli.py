"""yq CLI 根入口：聚合 factor / cache 子命令组。"""

import typer

from yq import __version__
from yq.cache import cache_app
from yq.factors import factor_app

app = typer.Typer(
    name="yq",
    help="yoyo-quant 命令行工具：因子注册表查询、计算、IC/IR 评估与缓存管理",
    pretty_exceptions_show_locals=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="显示版本号后退出", is_eager=True
    ),
) -> None:
    """yoyo-quant 命令行工具。"""
    if version:
        typer.echo(f"yq {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


app.add_typer(factor_app, name="factor", help="因子注册表查询、计算与评估")
app.add_typer(cache_app, name="cache", help="因子磁盘缓存统计与清理")
