"""yq cache 子命令：因子磁盘缓存统计与清理。"""

import json
from pathlib import Path

import typer

from factors.cache import clear_factor_cache, get_default_cache_dir

cache_app = typer.Typer(
    name="cache",
    help="因子磁盘缓存统计与清理",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _scan(cache_dir: str | Path) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """统计缓存：总文件数、总字节、按因子 (文件数, 字节)。"""
    root = Path(cache_dir)
    total_files = 0
    total_bytes = 0
    by_factor: dict[str, list[int]] = {}
    if root.exists():
        for p in root.rglob("*.parquet"):
            size = p.stat().st_size
            total_files += 1
            total_bytes += size
            factor_name = p.relative_to(root).parts[0]
            by_factor.setdefault(factor_name, [0, 0])
            by_factor[factor_name][0] += 1
            by_factor[factor_name][1] += size
    return total_files, total_bytes, {k: (v[0], v[1]) for k, v in by_factor.items()}


@cache_app.command("info")
def cache_info(
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="缓存目录（默认 FACTOR_CACHE_DIR 或 data/factors/）"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """统计缓存文件数与大小（按因子分组）。"""
    root = cache_dir if cache_dir is not None else get_default_cache_dir()
    total_files, total_bytes, by_factor = _scan(root)
    if json_out:
        payload = {
            "cache_dir": str(root),
            "file_count": total_files,
            "bytes": total_bytes,
            "by_factor": {
                name: {"files": n, "bytes": b} for name, (n, b) in by_factor.items()
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"缓存目录: {root}")
    typer.echo(f"文件数: {total_files}")
    typer.echo(f"大小: {total_bytes} B")
    for name in sorted(by_factor):
        n, b = by_factor[name]
        typer.echo(f"  {name}: {n} 个文件, {b} B")


@cache_app.command("clear")
def cache_clear(
    factor: str | None = typer.Option(
        None, "--factor", help="只清理该因子（默认清理全部）"
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="缓存目录（默认 FACTOR_CACHE_DIR 或 data/factors/）"
    ),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """删除因子缓存文件。"""
    root = cache_dir if cache_dir is not None else get_default_cache_dir()
    removed = clear_factor_cache(factor, root)
    if json_out:
        typer.echo(json.dumps({"removed": removed}, ensure_ascii=False, indent=2))
        return
    target = f"因子 {factor!r}" if factor else "全部"
    typer.echo(f"已清理{target}的 {removed} 个缓存文件")
