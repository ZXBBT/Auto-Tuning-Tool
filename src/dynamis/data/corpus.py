"""Curated, provenance-tracked log corpus.

The *right* way to collect real data for this project: each log enters with explicit
metadata (fuel, mods, hardware, source, consent) and must pass QA. This is what M3
calibration consumes. No scraping — small, well-characterized logs beat bulk anonymous
ones for fitting a physics model (see docs/data-feasibility.md).
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import yaml

from .ingest import load_csv
from .mapping import COBB_EA888, SourceProfile
from .qa import qa_report
from .schema import LogFrame

DEFAULT_CORPUS_DIR = "data/corpus"


# ----------------------------- metadata -----------------------------
@dataclass
class Source:
    type: str = "unknown"        # own_car | build_thread | dataset | donation
    url: str = ""
    retrieved: str = ""          # ISO date
    consent: str = ""            # license / consent / permission note


@dataclass
class Vehicle:
    platform: str = "EA888 Gen3"
    model: str = ""              # e.g. "MK7 GTI"
    year: str = ""
    turbo: str = ""              # IS20 | IS38 | hybrid  (changes the physics!)
    transmission: str = ""


@dataclass
class Fuel:
    octane_ron: float | None = None
    ethanol_pct: float | None = None
    brand: str = ""


@dataclass
class Ambient:
    temp_c: float | None = None
    pressure_kpa: float | None = None
    altitude_m: float | None = None


@dataclass
class Logging:
    tool: str = ""               # COBB Accessport | MHD | ...
    tool_version: str = ""
    units_note: str = ""         # note any non-default units in the raw file


@dataclass
class CorpusMeta:
    entry_id: str
    source: Source = field(default_factory=Source)
    vehicle: Vehicle = field(default_factory=Vehicle)
    fuel: Fuel = field(default_factory=Fuel)
    mods: list[str] = field(default_factory=list)
    health_notes: str = ""
    ambient: Ambient = field(default_factory=Ambient)
    logging: Logging = field(default_factory=Logging)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CorpusMeta":
        def sub(cls, val):
            allowed = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in (val or {}).items() if k in allowed})

        return CorpusMeta(
            entry_id=str(d.get("entry_id") or d.get("id") or "unnamed"),
            source=sub(Source, d.get("source")),
            vehicle=sub(Vehicle, d.get("vehicle")),
            fuel=sub(Fuel, d.get("fuel")),
            mods=list(d.get("mods") or []),
            health_notes=d.get("health_notes", ""),
            ambient=sub(Ambient, d.get("ambient")),
            logging=sub(Logging, d.get("logging")),
            notes=d.get("notes", ""),
        )

    @staticmethod
    def from_yaml(path: str) -> "CorpusMeta":
        with open(path) as fh:
            d = yaml.safe_load(fh) or {}
        if not d.get("entry_id") and not d.get("id"):
            d["entry_id"] = Path(path).stem
        return CorpusMeta.from_dict(d)


def validate_metadata(meta: CorpusMeta) -> list[str]:
    """Warn about missing context that materially affects calibration."""
    warns: list[str] = []
    if meta.fuel.octane_ron is None:
        warns.append("fuel.octane_ron missing — critical for the knock model")
    if not meta.vehicle.turbo:
        warns.append("vehicle.turbo missing (IS20/IS38/hybrid) — changes the air path")
    if not meta.mods:
        warns.append("mods empty — confirm the car is truly stock, don't leave blank by omission")
    if not meta.source.consent:
        warns.append("source.consent missing — record how this log was obtained / its license")
    return warns


# ----------------------------- corpus ops -----------------------------
@dataclass
class CorpusEntry:
    meta: CorpusMeta
    path: str
    qa: dict


@dataclass
class AddResult:
    ok: bool
    entry_id: str
    qa: dict
    problems: list[str]
    warnings: list[str]
    path: str | None = None


def _qa_problems(qa: dict) -> list[str]:
    problems = []
    if qa["channels_missing_required"]:
        problems.append(f"missing required channels: {qa['channels_missing_required']}")
    if qa["wot_segments"] == 0:
        problems.append("no WOT pull detected")
    if qa["range_violations"]:
        problems.append(f"range violations: {qa['range_violations']}")
    return problems


def add_log(
    csv_path: str,
    meta: CorpusMeta,
    corpus_dir: str = DEFAULT_CORPUS_DIR,
    profile: SourceProfile = COBB_EA888,
    force: bool = False,
) -> AddResult:
    """Validate a real log and file it into the corpus with its metadata."""
    lf: LogFrame = load_csv(csv_path, profile=profile)
    qa = qa_report(lf)
    problems = _qa_problems(qa)
    warnings = validate_metadata(meta)

    if problems and not force:
        return AddResult(False, meta.entry_id, qa, problems, warnings, None)

    entry_dir = Path(corpus_dir) / meta.entry_id
    entry_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(csv_path, entry_dir / "log.csv")
    with open(entry_dir / "metadata.yaml", "w") as fh:
        yaml.safe_dump(meta.to_dict(), fh, sort_keys=False)

    _update_index(corpus_dir, meta, qa)
    return AddResult(True, meta.entry_id, qa, problems, warnings, str(entry_dir))


def _update_index(corpus_dir: str, meta: CorpusMeta, qa: dict) -> None:
    index_path = Path(corpus_dir) / "index.yaml"
    index: list = []
    if index_path.exists():
        index = yaml.safe_load(index_path.read_text()) or []
    index = [e for e in index if e.get("entry_id") != meta.entry_id]
    index.append(
        {
            "entry_id": meta.entry_id,
            "model": meta.vehicle.model,
            "turbo": meta.vehicle.turbo,
            "fuel_ron": meta.fuel.octane_ron,
            "mods": meta.mods,
            "source_url": meta.source.url,
            "rows": qa["rows"],
            "wot_segments": qa["wot_segments"],
            "path": f"{meta.entry_id}/log.csv",
        }
    )
    with open(index_path, "w") as fh:
        yaml.safe_dump(index, fh, sort_keys=False)


def load_corpus(corpus_dir: str = DEFAULT_CORPUS_DIR) -> list[CorpusEntry]:
    root = Path(corpus_dir)
    if not root.exists():
        return []
    entries = []
    for meta_path in sorted(root.glob("*/metadata.yaml")):
        meta = CorpusMeta.from_dict(yaml.safe_load(meta_path.read_text()) or {})
        log_path = meta_path.parent / "log.csv"
        qa = qa_report(load_csv(str(log_path))) if log_path.exists() else {}
        entries.append(CorpusEntry(meta=meta, path=str(log_path), qa=qa))
    return entries
