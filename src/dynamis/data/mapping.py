"""Source-tool column mapping profiles.

A `SourceProfile` knows how to translate a specific logging tool's columns into the
canonical schema: which source column names (aliases) feed which canonical channel, and
what source unit each is in. Profiles are deliberately data — real files let us refine
the aliases/units without touching ingestion logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def normalize_name(name: str) -> str:
    """Lowercase + strip non-alphanumerics for robust column matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass(frozen=True)
class ColumnSpec:
    canonical: str          # canonical channel key
    aliases: tuple[str, ...]  # possible source column names
    unit: str               # source unit (see units.to_canonical)


@dataclass
class SourceProfile:
    name: str
    columns: list[ColumnSpec]
    afr_stoich: float = 14.7

    def find(self, source_columns: list[str]) -> dict[str, str]:
        """Map canonical key -> matching source column name (if present)."""
        norm_to_src = {normalize_name(c): c for c in source_columns}
        out: dict[str, str] = {}
        for spec in self.columns:
            for alias in spec.aliases:
                hit = norm_to_src.get(normalize_name(alias))
                if hit is not None:
                    out[spec.canonical] = hit
                    break
        return out


# COBB Accessport / Accesstuner profile for EA888 (MK7 GTI/Golf R).
# Unit defaults reflect common US-market COBB logs; override per file if needed.
COBB_EA888 = SourceProfile(
    name="COBB Accessport — EA888 (MK7)",
    afr_stoich=14.7,
    columns=[
        ColumnSpec("time_s", ("Time", "Time (sec)", "Timestamp"), "s"),
        ColumnSpec("rpm", ("Engine Speed", "RPM", "Engine Speed (RPM)"), "rpm"),
        ColumnSpec("boost_kpa", ("Boost Pressure", "Boost", "Boost Pressure (psi)"), "psi_gauge"),
        ColumnSpec("map_kpa", ("Intake Manifold Pressure", "MAP", "Manifold Pressure"), "psi_abs"),
        ColumnSpec("charge_temp_c", ("Charge Air Temp", "Charge Air Temperature", "CAT"), "degC"),
        ColumnSpec("iat_c", ("Intake Air Temp", "IAT", "Intake Air Temperature"), "degC"),
        ColumnSpec(
            "air_mass_per_stroke_mg",
            ("Air Mass Intake Manifold Per Stroke", "Air Mass Per Stroke", "Mass Air Per Stroke"),
            "g_per_stroke",
        ),
        ColumnSpec("lambda", ("AFR", "Air Fuel Ratio", "AFR Actual"), "afr"),
        ColumnSpec("lambda_target", ("AFR Set Point", "AFR Target", "Target AFR"), "afr"),
        ColumnSpec("ignition_deg", ("Ignition Timing Final", "Ignition Timing", "Timing"), "deg"),
        ColumnSpec("knock_retard_cyl1", ("Knock Retard Cylinder 1", "Knock Retard Cyl 1", "KR Cyl 1"), "deg"),
        ColumnSpec("knock_retard_cyl2", ("Knock Retard Cylinder 2", "Knock Retard Cyl 2", "KR Cyl 2"), "deg"),
        ColumnSpec("knock_retard_cyl3", ("Knock Retard Cylinder 3", "Knock Retard Cyl 3", "KR Cyl 3"), "deg"),
        ColumnSpec("knock_retard_cyl4", ("Knock Retard Cylinder 4", "Knock Retard Cyl 4", "KR Cyl 4"), "deg"),
        ColumnSpec("cam_intake_deg", ("Intake Cam Position", "Intake Cam", "Intake Camshaft Position"), "deg"),
        ColumnSpec("cam_exhaust_deg", ("Exhaust Cam Position", "Exhaust Cam", "Exhaust Camshaft Position"), "deg"),
        ColumnSpec("wastegate_pct", ("Wastegate Valve Position", "Wastegate Duty", "WGDC", "Wastegate"), "pct"),
        ColumnSpec("injection_time_ms", ("Injection Time", "Injector Pulse Width", "Injection Time Primary"), "ms"),
        ColumnSpec("pedal_pct", ("Accel Pedal Position", "Pedal", "Accelerator Pedal Position"), "pct"),
        ColumnSpec("gear", ("Current Gear", "Gear"), "gear"),
    ],
)
