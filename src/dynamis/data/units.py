"""Unit conversion to canonical units.

`source_unit` strings encode what the raw column is in; `to_canonical` returns the value
in this project's canonical unit for that quantity (see schema). AFR needs the engine's
stoichiometric ratio and is handled by the ingester, not here.
"""

from __future__ import annotations

import pandas as pd

PSI_TO_KPA = 6.894757
P_ATM_KPA = 101.325

# units that are already canonical / dimensionless and pass through unchanged
_PASSTHROUGH = {"rpm", "s", "deg", "degBTDC", "pct", "%", "ms", "lambda", "-", "count", "gear", "kpa_abs", "kpa_gauge", "degc"}


def to_canonical(series: pd.Series, source_unit: str) -> pd.Series:
    u = source_unit.lower()
    s = series.astype(float)
    if u in _PASSTHROUGH:
        return s
    if u in ("psi_gauge", "psi_abs", "psi"):
        return s * PSI_TO_KPA
    if u in ("bar_gauge", "bar_abs", "bar"):
        return s * 100.0
    if u == "degf":
        return (s - 32.0) * 5.0 / 9.0
    if u == "g_per_stroke":
        return s * 1000.0  # g -> mg
    if u == "mg_per_stroke":
        return s
    raise ValueError(f"unknown source unit: {source_unit!r}")
