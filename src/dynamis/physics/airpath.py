"""Air path — speed-density cylinder air flow.

v0 conditions on the *measured* manifold pressure (from the log / a sweep) rather than
solving the turbo. The turbo + wastegate solve (predicting boost from actuator) is
needed for the optimizer's boost decision variable and arrives with the transient work.
"""

from __future__ import annotations

from ..config.engine import EngineParams
from .constants import N_REV_PER_CYCLE, R_AIR


def trapped_air_mass_per_cycle(
    p_im_pa: float, T_im_k: float, eta_vol: float, params: EngineParams
) -> float:
    """Total (all cylinders) trapped air mass per engine cycle [kg]."""
    return eta_vol * p_im_pa * params.displacement_m3 / (R_AIR * T_im_k)


def air_mass_flow(
    rpm: float, p_im_pa: float, T_im_k: float, eta_vol: float, params: EngineParams
) -> float:
    """Engine air mass flow [kg/s]."""
    m_cycle = trapped_air_mass_per_cycle(p_im_pa, T_im_k, eta_vol, params)
    cycles_per_s = (rpm / 60.0) / N_REV_PER_CYCLE
    return m_cycle * cycles_per_s
