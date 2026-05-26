"""Parameter routing: map market regime to strategy parameters.

Unlike ``regime_switch`` which routes to different *strategies*, this module
routes to different *parameter sets* for the same strategy. The two compose:
regime_switch selects the strategy, param_router tunes it for the current regime.

Rationale (from 2026-05-26 per-regime audit):
    - Factor stability rankings are highly stable across regimes →
      per-regime factor weight switching provides minimal value.
    - But trading frequency (rebalance) and position concentration (top_n)
      ARE regime-dependent:
      - trend_up: faster rebalance (confirmed trend)
      - trend_down: fewer positions (defensive)
      - volatile: very fast rebalance + fewer positions (nimble)
      - range: normal
"""

from __future__ import annotations

# Default parameter sets per regime.
# Tuned on 30 CSI 300 stocks, 2023-2026.
DEFAULT_REGIME_PARAMS: dict[str, dict] = {
    "trend_up": {
        "rebalance": 10,   # faster: trend confirmed, stay aligned
        "top_n": 5,
        "bottom_n": 3,
    },
    "trend_down": {
        "rebalance": 20,   # normal: don't overtrade in downtrend
        "top_n": 3,        # defensive: fewer longs
        "bottom_n": 5,     # more shorts
    },
    "range": {
        "rebalance": 20,   # normal: mean-reversion takes time
        "top_n": 5,
        "bottom_n": 3,
    },
    "volatile": {
        "rebalance": 5,    # nimble: high vol → fast entry/exit
        "top_n": 3,        # light: reduce exposure
        "bottom_n": 3,
    },
}


def route_params(
    regime: str,
    params_map: dict[str, dict] | None = None,
) -> dict:
    """Return strategy parameters for a given regime.

    Parameters
    ----------
    regime : str
        One of "trend_up", "trend_down", "range", "volatile".
    params_map : dict or None
        Override the default ``DEFAULT_REGIME_PARAMS`` mapping.
        Keys are regime labels, values are ``{param_name: value}`` dicts.

    Returns
    -------
    dict
        Parameter dict suitable for passing to ``get_strategy(name, **params)``.
        Returns the "range" default for unknown regimes.
    """
    mapping = params_map if params_map is not None else DEFAULT_REGIME_PARAMS
    return dict(mapping.get(regime, mapping.get("range", {})))
