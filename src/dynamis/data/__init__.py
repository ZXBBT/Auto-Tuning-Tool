"""Data layer (M1): ingest heterogeneous ECU logs into one canonical schema + QA."""

from .ingest import ingest_dataframe, load_csv
from .mapping import COBB_EA888, SourceProfile
from .qa import detect_wot_segments, qa_report
from .schema import CANONICAL_CHANNELS, LogFrame
from .synthetic import generate_cobb_wot_log

__all__ = [
    "ingest_dataframe",
    "load_csv",
    "COBB_EA888",
    "SourceProfile",
    "detect_wot_segments",
    "qa_report",
    "CANONICAL_CHANNELS",
    "LogFrame",
    "generate_cobb_wot_log",
]
