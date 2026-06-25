"""The unified, normalized log schema (ARCHITECTURE 8.1).

Heterogeneous tool exports are mapped onto these canonical channels with canonical units.
Missing channels are flagged, never fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Channel:
    key: str          # canonical column name
    unit: str         # canonical unit
    required: bool    # is this channel required for downstream use?
    description: str


CANONICAL_CHANNELS: list[Channel] = [
    Channel("time_s", "s", True, "monotonic time"),
    Channel("rpm", "rpm", True, "engine speed"),
    Channel("map_kpa", "kPa_abs", True, "manifold absolute pressure"),
    Channel("boost_kpa", "kPa_gauge", False, "boost (gauge)"),
    Channel("iat_c", "degC", False, "intake air temperature"),
    Channel("charge_temp_c", "degC", False, "charge air temperature (post-intercooler)"),
    Channel("air_mass_per_stroke_mg", "mg", False, "air mass per cylinder per stroke (VE proxy)"),
    Channel("lambda", "-", False, "measured lambda"),
    Channel("lambda_target", "-", False, "commanded lambda"),
    Channel("ignition_deg", "degBTDC", False, "final ignition timing"),
    Channel("knock_retard_deg", "deg", False, "aggregate knock retard (max over cylinders)"),
    Channel("knock_retard_cyl1", "deg", False, "knock retard cylinder 1"),
    Channel("knock_retard_cyl2", "deg", False, "knock retard cylinder 2"),
    Channel("knock_retard_cyl3", "deg", False, "knock retard cylinder 3"),
    Channel("knock_retard_cyl4", "deg", False, "knock retard cylinder 4"),
    Channel("cam_intake_deg", "deg", False, "intake cam position"),
    Channel("cam_exhaust_deg", "deg", False, "exhaust cam position"),
    Channel("wastegate_pct", "%", False, "wastegate / boost actuator position"),
    Channel("injection_time_ms", "ms", False, "injector pulse width"),
    Channel("pedal_pct", "%", False, "accelerator pedal position"),
    Channel("gear", "-", False, "current gear"),
]

CANONICAL_KEYS = {c.key for c in CANONICAL_CHANNELS}
REQUIRED_KEYS = {c.key for c in CANONICAL_CHANNELS if c.required}


@dataclass
class LogFrame:
    """A normalized log: canonical-column DataFrame + provenance + missing-channel report."""

    df: pd.DataFrame
    meta: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def channels(self) -> list[str]:
        return list(self.df.columns)

    def __len__(self) -> int:
        return len(self.df)
