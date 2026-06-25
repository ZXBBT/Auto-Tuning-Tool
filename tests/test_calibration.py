"""Parameter-recovery tests for the M3 calibration machinery (on sim data)."""

from __future__ import annotations

from dataclasses import replace

from dynamis.calibration.dataset import label_dataset, make_grid
from dynamis.calibration.fit import calibrate
from dynamis.config import EA888_GEN3


def test_recover_volumetric_efficiency():
    true = replace(EA888_GEN3, ve_peak=0.96, ve_rpm_peak=4800.0)
    df = label_dataset(make_grid(), true, ["air_mass_per_stroke_mg"])
    res = calibrate(
        df, EA888_GEN3, ["ve_peak", "ve_rpm_peak"], ["air_mass_per_stroke_mg"],
        init=[EA888_GEN3.ve_peak, EA888_GEN3.ve_rpm_peak],
        bounds=[(0.6, 1.1), (2000.0, 7000.0)],
    )
    assert abs(res.fitted["ve_peak"] - 0.96) < 0.01
    assert abs(res.fitted["ve_rpm_peak"] - 4800.0) < 250.0
    assert res.rmse["air_mass_per_stroke_mg"] < 1.0


def test_recover_efficiency_and_friction():
    true = replace(EA888_GEN3, eta_thermal_base=0.39, fmep_pa=1.7e5)
    df = label_dataset(make_grid(), true, ["torque_nm"])
    res = calibrate(
        df, EA888_GEN3, ["eta_thermal_base", "fmep_pa"], ["torque_nm"],
        init=[EA888_GEN3.eta_thermal_base, EA888_GEN3.fmep_pa],
        bounds=[(0.25, 0.45), (0.5e5, 3.0e5)],
    )
    assert abs(res.fitted["eta_thermal_base"] - 0.39) < 0.01
    assert abs(res.fitted["fmep_pa"] - 1.7e5) < 0.15e5


def test_recover_knock_constant():
    true = replace(EA888_GEN3, knock_A=21.0)
    df = label_dataset(make_grid(), true, ["knock_limited_deg"])
    res = calibrate(
        df, EA888_GEN3, ["knock_A"], ["knock_limited_deg"],
        init=[EA888_GEN3.knock_A], bounds=[(5.0, 40.0)],
    )
    assert abs(res.fitted["knock_A"] - 21.0) < 1.5
