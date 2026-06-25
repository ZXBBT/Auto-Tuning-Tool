"""Lightweight target predictors for calibration.

These compute only what each target needs (avoiding the full simulate_wot / knock loop
where possible), so least-squares fitting stays fast.
"""

from __future__ import annotations

from ..config.engine import EngineParams
from ..physics.airpath import air_mass_flow
from ..physics.combustion import brake_torque_power, mbt_spark_deg
from ..physics.constants import N_REV_PER_CYCLE, WATT_PER_HP
from ..physics.fueling import charge_cooling_delta_T, fuel_mass_flow
from ..physics.knock import knock_limited_spark
from ..physics.volumetric import volumetric_efficiency

CHEAP_TARGETS = {"air_mass_per_stroke_mg", "torque_nm", "power_hp"}


def predict_cheap(eng: EngineParams, rpm, p_im_pa, charge_temp_k, lam, octane, spark_deg) -> dict:
    eta_vol = volumetric_efficiency(rpm, p_im_pa, eng)
    m_dot_air = air_mass_flow(rpm, p_im_pa, charge_temp_k, eta_vol, eng)
    cps = (rpm / 60.0) / N_REV_PER_CYCLE
    airmass_mg = m_dot_air / cps / eng.num_cylinders * 1e6
    m_dot_fuel = fuel_mass_flow(m_dot_air, lam, eng)
    m_dot_fuel_burn = min(m_dot_fuel, m_dot_air / eng.afr_stoich)
    mbt = mbt_spark_deg(rpm, p_im_pa, eng)
    torque, p_brake = brake_torque_power(rpm, m_dot_fuel_burn, spark_deg, mbt, eng)
    return {
        "air_mass_per_stroke_mg": airmass_mg,
        "torque_nm": torque,
        "power_hp": p_brake / WATT_PER_HP,
    }


def predict_knock_limited_deg(eng: EngineParams, rpm, p_im_pa, charge_temp_k, lam, octane, **_) -> float:
    t_knock = charge_temp_k - charge_cooling_delta_T(lam, eng)
    eta_vol = volumetric_efficiency(rpm, p_im_pa, eng)
    m_dot_air = air_mass_flow(rpm, p_im_pa, charge_temp_k, eta_vol, eng)
    cps = (rpm / 60.0) / N_REV_PER_CYCLE
    m_air_cyl = m_dot_air / cps / eng.num_cylinders
    m_dot_fuel = fuel_mass_flow(m_dot_air, lam, eng)
    m_fuel_burn_cyl = min(m_dot_fuel, m_dot_air / eng.afr_stoich) / cps / eng.num_cylinders
    kls, _ = knock_limited_spark(rpm, t_knock, m_air_cyl, m_fuel_burn_cyl, octane, eng)
    return kls
