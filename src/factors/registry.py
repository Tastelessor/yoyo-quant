"""Factor registry: register and retrieve factor functions by name or alias."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

FACTOR_REGISTRY: dict[str, tuple[Callable[[pd.DataFrame], pd.Series], list[str]]] = {}


def register_factor(
    name: str,
    func: Callable[[pd.DataFrame], pd.Series],
    tags: list[str] | None = None,
) -> None:
    """Register a factor function under *name*."""
    FACTOR_REGISTRY[name] = (func, tags or [])


def get_factor(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    """Look up a registered factor by name. Raises KeyError if not found."""
    if name not in FACTOR_REGISTRY:
        raise KeyError(f"Unknown factor: {name!r}")
    return FACTOR_REGISTRY[name][0]


def list_factors(tag: str | None = None) -> list[str]:
    """List registered factor names, optionally filtered by tag."""
    if tag is None:
        return list(FACTOR_REGISTRY.keys())
    return [name for name, (_, tags) in FACTOR_REGISTRY.items() if tag in tags]


def calc_factors(
    df: pd.DataFrame,
    factor_names: list[str],
) -> pd.DataFrame:
    """Compute multiple factors and assemble into a DataFrame.

    Returns DataFrame with columns: date, code, <factor_name_1>, ...
    """
    df_sorted = df.sort_values(["code", "date"]).reset_index(drop=True)
    result = df_sorted[["date", "code"]].copy()
    for name in factor_names:
        func = get_factor(name)
        result[name] = func(df_sorted).values
    return result


def _register_defaults() -> None:
    """Auto-register all GTJA momentum factors with primary names and aliases."""
    from src.factors.momentum import (
        calc_momentum_5d_change,
        calc_momentum_5d_ratio,
        calc_momentum_6d_return,
        calc_momentum_20d_change,
        calc_momentum_20d_return,
    )

    momentum_factors = [
        ("calc_momentum_5d_change", calc_momentum_5d_change, "gtja_14"),
        ("calc_momentum_5d_ratio", calc_momentum_5d_ratio, "gtja_18"),
        ("calc_momentum_6d_return", calc_momentum_6d_return, "gtja_20"),
        ("calc_momentum_20d_return", calc_momentum_20d_return, "gtja_88"),
        ("calc_momentum_20d_change", calc_momentum_20d_change, "gtja_106"),
    ]
    for primary_name, func, alias in momentum_factors:
        register_factor(primary_name, func, tags=["momentum", "gtja"])
        register_factor(alias, func, tags=["momentum", "gtja"])


_register_defaults()
