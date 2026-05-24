"""Rule ABC and RuleContext for the composable rule engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class RuleContext:
    """Data bus shared across rules.

    Rules read from and write to this context. They communicate
    indirectly through ``metadata`` rather than importing each other.
    """

    signals: pd.DataFrame
    positions: pd.DataFrame
    market_data: pd.DataFrame
    metadata: dict = field(default_factory=dict)


class Rule(ABC):
    """Abstract base class for all risk / strategy rules.

    Subclasses must define ``name``, ``priority``, and ``apply``.

    Priority zones
    --------------
    - 0-99:   signal generation (strategies)
    - 100-199: risk filtering (stop-loss, position limits)
    - 200-299: trade constraints (T+1, limit price)
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def priority(self) -> int: ...

    @abstractmethod
    def apply(self, ctx: RuleContext) -> RuleContext: ...
