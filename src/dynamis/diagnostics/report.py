"""Assemble detectors into a diagnostic report."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import EA888_GEN3
from ..config.engine import EngineParams
from ..data.qa import detect_wot_segments
from ..data.schema import LogFrame
from .detectors import (
    Finding,
    detect_boost,
    detect_fueling,
    detect_knock,
    estimate_timing_headroom,
)

_ICON = {"info": "·", "low": "•", "medium": "▲", "high": "⚠"}
_ORDER = ["knock", "fueling", "boost", "timing", "general"]


@dataclass
class DiagnosticReport:
    findings: list[Finding]
    wot_rpm: tuple | None
    est_power_left_hp: float
    meta: dict = field(default_factory=dict)

    def render(self) -> str:
        lines = ["=== Diagnostic report ==="]
        who = self.meta.get("vehicle") or self.meta.get("source_path")
        if who:
            lines.append(str(who))
        if self.wot_rpm:
            lines.append(f"WOT pull: {int(self.wot_rpm[0])}-{int(self.wot_rpm[1])} rpm")
        for cat in _ORDER:
            fs = [f for f in self.findings if f.category == cat]
            if not fs:
                continue
            lines.append(f"\n[{cat.upper()}]")
            for f in fs:
                tag = " (model)" if f.source == "model-estimated" else ""
                lines.append(f"  {_ICON.get(f.severity, '·')} {f.message}{tag}")
        lines.append(f"\nEstimated power left on the table: ~{self.est_power_left_hp:.0f} hp (model-estimated)")
        return "\n".join(lines)


def diagnose(lf: LogFrame, engine: EngineParams = EA888_GEN3, octane: float = 98.0) -> DiagnosticReport:
    df = lf.df
    segments = detect_wot_segments(df)
    if not segments:
        return DiagnosticReport([Finding("general", "info", "no WOT pull detected in this log")], None, 0.0, lf.meta)

    a, b = max(segments, key=lambda s: s[1] - s[0])  # largest pull
    seg = df.iloc[a : b + 1].reset_index(drop=True)

    findings: list[Finding] = []
    findings += detect_knock(seg)
    findings += detect_fueling(seg)
    findings += detect_boost(seg)
    th, est_left = estimate_timing_headroom(seg, engine, octane)
    findings += th

    wot = (float(seg["rpm"].iloc[0]), float(seg["rpm"].iloc[-1]))
    return DiagnosticReport(findings, wot, est_left, lf.meta)
