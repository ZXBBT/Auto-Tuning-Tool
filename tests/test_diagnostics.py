"""Tests for the M5 diagnostics (torch-free)."""

from __future__ import annotations

import pandas as pd

from dynamis.data import COBB_EA888, generate_cobb_wot_log, ingest_dataframe
from dynamis.diagnostics import diagnose
from dynamis.diagnostics.detectors import detect_fueling, detect_knock


def _diag(spark_offset):
    raw = generate_cobb_wot_log(seed=3, spark_offset_deg=spark_offset)
    return diagnose(ingest_dataframe(raw, COBB_EA888), octane=98.0)


def test_conservative_tune_shows_timing_headroom():
    rep = _diag(spark_offset=-4.0)
    assert rep.est_power_left_hp > 3.0
    assert any(f.category == "timing" and f.severity == "medium" for f in rep.findings)


def test_optimal_tune_has_little_headroom():
    rep = _diag(spark_offset=0.0)
    assert rep.est_power_left_hp < 8.0


def test_detects_lean_excursion():
    df = pd.DataFrame(
        {
            "rpm": [4000, 4500, 5000, 5500],
            "lambda": [0.85, 0.97, 0.86, 0.85],  # one lean spike vs target
            "lambda_target": [0.85, 0.85, 0.85, 0.85],
        }
    )
    findings = detect_fueling(df)
    assert any(f.category == "fueling" and f.severity == "high" for f in findings)


def test_knock_detector_flags_retard():
    df = pd.DataFrame({"rpm": [5000, 5200, 5400], "knock_retard_deg": [0.0, 2.5, 0.3]})
    findings = detect_knock(df)
    assert any(f.category == "knock" and f.severity in ("medium", "high") for f in findings)


def test_clean_log_reports_no_knock():
    df = pd.DataFrame({"rpm": [5000, 5200], "knock_retard_deg": [0.0, 0.0]})
    findings = detect_knock(df)
    assert all(f.severity == "info" for f in findings)
