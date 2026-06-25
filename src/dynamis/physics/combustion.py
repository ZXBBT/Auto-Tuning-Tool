"""Combustion & torque — mean-value indicated work, spark efficiency, friction."""

from __future__ import annotations

import math

from ..config.engine import EngineParams
from .constants import N_REV_PER_CYCLE, P_ATM


def mbt_spark_deg(rpm: float, p_im_pa: float, params: EngineParams) -> float:
    """Knock-free Minimum spark advance for Best Torque [deg BTDC] (placeholder model)."""
    boost_bar = (p_im_pa - P_ATM) / 1e5
    mbt = (
        params.mbt_base_deg
        - params.mbt_k_load * max(0.0, boost_bar)
        + params.mbt_k_rpm * (rpm - 3000.0) / 1000.0
    )
    return min(32.0, max(6.0, mbt))


def spark_efficiency(spark_deg: float, mbt_deg: float, params: EngineParams) -> float:
    """Torque fraction relative to MBT given spark retard from MBT."""
    retard = max(0.0, mbt_deg - spark_deg)
    return max(0.5, 1.0 - params.spark_eff_k * retard * retard)


def friction_power(rpm: float, params: EngineParams) -> float:
    cycles_per_s = (rpm / 60.0) / N_REV_PER_CYCLE
    return params.fmep_pa * params.displacement_m3 * cycles_per_s


def brake_torque_power(
    rpm: float, m_dot_fuel: float, spark_deg: float, mbt_deg: float, params: EngineParams
) -> tuple[float, float]:
    """Return (brake torque [N*m], brake power [W])."""
    p_ind = (
        m_dot_fuel
        * params.fuel_lhv
        * params.eta_combustion
        * params.eta_thermal_base
        * spark_efficiency(spark_deg, mbt_deg, params)
    )
    p_brake = p_ind - friction_power(rpm, params)
    omega = 2.0 * math.pi * rpm / 60.0
    torque = p_brake / omega if omega > 0 else 0.0
    return torque, p_brake
