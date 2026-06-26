"""Diagnostics (M5): read a log -> a bottleneck report.

Separates *observed* findings (knock retard, AFR vs target, boost droop — straight from
the log) from *model-estimated* ones (timing headroom, power left on the table — via the
MVEM, so subject to the uncalibrated-sim caveat).
"""

from .detectors import Finding
from .report import DiagnosticReport, diagnose

__all__ = ["Finding", "DiagnosticReport", "diagnose"]
