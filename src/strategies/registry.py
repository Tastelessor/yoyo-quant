"""Strategy registry: register and retrieve strategies by name."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strategies.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(name: str):
    """Decorator to register a strategy class under *name*."""

    def decorator(cls: type[Strategy]) -> type[Strategy]:
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy(name: str, **params) -> Strategy:
    """Instantiate a registered strategy by *name*."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy: {name!r}")
    return _REGISTRY[name](**params)


def list_strategies() -> list[str]:
    """Return names of all registered strategies."""
    return list(_REGISTRY.keys())
