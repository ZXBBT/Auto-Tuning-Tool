"""Ingestion: raw tool CSV / DataFrame -> canonical LogFrame."""

from __future__ import annotations

import pandas as pd

from .mapping import COBB_EA888, SourceProfile
from .schema import REQUIRED_KEYS, LogFrame
from .units import P_ATM_KPA, to_canonical

_PER_CYL_KNOCK = ["knock_retard_cyl1", "knock_retard_cyl2", "knock_retard_cyl3", "knock_retard_cyl4"]


def ingest_dataframe(
    raw: pd.DataFrame, profile: SourceProfile = COBB_EA888, meta: dict | None = None
) -> LogFrame:
    """Map a raw tool DataFrame onto the canonical schema + normalize units."""
    found = profile.find(list(raw.columns))
    out = pd.DataFrame()

    for canonical, src_col in found.items():
        spec = next(c for c in profile.columns if c.canonical == canonical)
        col = raw[src_col]
        if spec.unit == "afr":
            out[canonical] = col.astype(float) / profile.afr_stoich  # AFR -> lambda
        else:
            out[canonical] = to_canonical(col, spec.unit)

    _derive(out)

    missing = sorted(REQUIRED_KEYS - set(out.columns))
    md = {"source_profile": profile.name, "n_source_columns": len(raw.columns)}
    if meta:
        md.update(meta)
    return LogFrame(df=out.reset_index(drop=True), meta=md, missing=missing)


def _derive(out: pd.DataFrame) -> None:
    """Fill cheaply-derivable channels from what's present."""
    has = set(out.columns)

    # boost <-> MAP (gauge vs absolute)
    if "map_kpa" not in has and "boost_kpa" in has:
        out["map_kpa"] = out["boost_kpa"] + P_ATM_KPA
    if "boost_kpa" not in has and "map_kpa" in has:
        out["boost_kpa"] = out["map_kpa"] - P_ATM_KPA

    # aggregate knock retard = worst (max) over available cylinders
    cyl = [c for c in _PER_CYL_KNOCK if c in out.columns]
    if cyl and "knock_retard_deg" not in out.columns:
        out["knock_retard_deg"] = out[cyl].max(axis=1)


def load_csv(path: str, profile: SourceProfile = COBB_EA888, meta: dict | None = None) -> LogFrame:
    raw = pd.read_csv(path)
    md = {"source_path": str(path)}
    if meta:
        md.update(meta)
    return ingest_dataframe(raw, profile=profile, meta=md)
