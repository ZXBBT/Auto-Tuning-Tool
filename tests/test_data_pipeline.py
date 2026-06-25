"""Tests for the M1 data layer: ingestion, unit normalization, derivation, QA."""

from __future__ import annotations

import pandas as pd

from dynamis.data import (
    COBB_EA888,
    detect_wot_segments,
    generate_cobb_wot_log,
    ingest_dataframe,
    qa_report,
)
from dynamis.data.units import P_ATM_KPA, to_canonical


def test_ingest_maps_canonical_channels():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=2), COBB_EA888)
    for key in ("time_s", "rpm", "map_kpa", "boost_kpa", "lambda", "ignition_deg"):
        assert key in lf.df.columns
    assert lf.missing == []  # all required channels present


def test_afr_converted_to_lambda():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=3, lam=0.85), COBB_EA888)
    wot = lf.df[lf.df["pedal_pct"] >= 95]
    assert 0.80 <= wot["lambda"].mean() <= 0.90  # ~0.85 target


def test_map_is_absolute_above_boost_gauge():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=4), COBB_EA888)
    diff = (lf.df["map_kpa"] - lf.df["boost_kpa"]).mean()
    assert abs(diff - P_ATM_KPA) < 1.0  # MAP(abs) = boost(gauge) + 1 atm


def test_boost_derived_when_missing():
    raw = generate_cobb_wot_log(seed=5).drop(columns=["Boost Pressure"])
    lf = ingest_dataframe(raw, COBB_EA888)
    assert "boost_kpa" in lf.df.columns  # derived from MAP


def test_aggregate_knock_retard():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=6), COBB_EA888)
    assert "knock_retard_deg" in lf.df.columns
    assert (lf.df["knock_retard_deg"] >= 0).all()


def test_wot_segment_detected():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=7), COBB_EA888)
    segs = detect_wot_segments(lf.df)
    assert len(segs) >= 1
    a, b = segs[0]
    assert lf.df["rpm"].iloc[b] - lf.df["rpm"].iloc[a] > 3000  # a real pull


def test_qa_report_clean():
    lf = ingest_dataframe(generate_cobb_wot_log(seed=8), COBB_EA888)
    rep = qa_report(lf)
    assert rep["wot_segments"] >= 1
    assert rep["channels_missing_required"] == []
    assert rep["range_violations"] == {}  # synthetic data stays in range


def test_unit_conversions():
    assert abs(to_canonical(pd.Series([10.0]), "psi_gauge").iloc[0] - 68.94757) < 1e-3
    assert abs(to_canonical(pd.Series([32.0]), "degF").iloc[0] - 0.0) < 1e-6
    assert abs(to_canonical(pd.Series([1.0]), "g_per_stroke").iloc[0] - 1000.0) < 1e-6
