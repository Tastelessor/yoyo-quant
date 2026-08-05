"""Rule engine: executes rules in priority order."""

from __future__ import annotations

from risk.rules import Rule, RuleContext


class RuleEngine:
    """Execute a list of rules sorted by priority.

    The engine is intentionally dumb — it loops through rules and
    calls ``apply`` in priority order. All business logic lives in
    the rules themselves.
    """

    def __init__(self, rules: list[Rule]):
        self.rules = sorted(rules, key=lambda r: r.priority)

    def run(self, ctx: RuleContext) -> RuleContext:
        for rule in self.rules:
            ctx = rule.apply(ctx)
        return ctx
