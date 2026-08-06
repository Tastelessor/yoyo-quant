"""factors 分层卫生测试：顶层(registry/operators) + builtin(因子实现) + ops(操作)。"""
import importlib

BUILTIN = [
    "momentum", "volume_price_gtja", "volatility_gtja", "mean_reversion",
    "trend", "vwap", "volatility", "volume_price", "cointegration",
    "earnings", "value", "quality", "liquidity",
]
OPS = ["evaluation", "neutralize", "cache"]


def test_builtin_modules_importable():
    for m in BUILTIN:
        importlib.import_module(f"factors.builtin.{m}")


def test_ops_modules_importable():
    for m in OPS:
        importlib.import_module(f"factors.ops.{m}")


def test_top_level_modules_importable():
    for m in ["registry", "operators"]:
        importlib.import_module(f"factors.{m}")


def test_top_level_reexports_work():
    from factors import (  # noqa: F401
        calc_hv,
        calc_momentum_5d_change,
        compute_ic,
        list_factors,
        neutralize_factors,
    )
