"""Top-level steady-state WOT mean-value engine model.

Conditions on an operating point (rpm, manifold pressure, charge temp, lambda, octane)
and returns brake torque/power, the knock-limited spark and the spark actually used,
knock margin, and an (approximate) EGT. This is the v0 physics-informed forward model.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.engine import EngineParams
from .airpath import air_mass_flow
from .combustion import brake_torque_power, mbt_spark_deg
from .constants import N_REV_PER_CYCLE, P_ATM, WATT_PER_HP
from .fueling import afr_from_lambda, charge_cooling_delta_T, fuel_mass_flow
from .knock import knock_integral, knock_limited_spark
from .volumetric import volumetric_efficiency


@dataclass
class OperatingPoint:
    rpm: float
    p_im_pa: float           # manifold absolute pressure [Pa]
    charge_temp_k: float     # manifold/charge gas temperature [K]
    lam: float = 0.85        # lambda (rich power band)
    octane: float = 98.0     # RON


@dataclass
class MvemResult:
    rpm: float
    eta_vol: float
    m_dot_air: float
    m_dot_fuel: float
    afr: float
    mbt_deg: float
    knock_limited_deg: float
    spark_deg: float
    knock_limited: bool
    knock_unavoidable: bool
    knock_margin: float
    torque_nm: float
    power_kw: float
    power_hp: float
    egt_c: float


def _per_cylinder_masses(op: OperatingPoint, eta_vol: float, params: EngineParams):
    m_dot_air = air_mass_flow(op.rpm, op.p_im_pa, op.charge_temp_k, eta_vol, params)
    m_dot_fuel = fuel_mass_flow(m_dot_air, op.lam, params)
    # Heat release is air-limited: fuel beyond stoichiometric cannot burn (no O2); it only
    # cools the charge (charge_cooling uses total fuel). So combustion uses burnable fuel.
    m_dot_fuel_burn = min(m_dot_fuel, m_dot_air / params.afr_stoich)
    cps = (op.rpm / 60.0) / N_REV_PER_CYCLE
    m_air_cyl = m_dot_air / cps / params.num_cylinders
    m_fuel_burn_cyl = m_dot_fuel_burn / cps / params.num_cylinders
    return m_dot_air, m_dot_fuel, m_dot_fuel_burn, m_air_cyl, m_fuel_burn_cyl


def simulate_wot(
    op: OperatingPoint, params: EngineParams, spark_deg: float | None = None
) -> MvemResult:
    """Simulate one steady-state WOT operating point.

    If `spark_deg` is None, the model runs the best safe spark = min(MBT, knock limit).
    """
    eta_vol = volumetric_efficiency(op.rpm, op.p_im_pa, params)
    m_dot_air, m_dot_fuel, m_dot_fuel_burn, m_air_cyl, m_fuel_burn_cyl = _per_cylinder_masses(
        op, eta_vol, params
    )

    # effective end-gas charge temperature including DI evaporative cooling
    t_knock = op.charge_temp_k - charge_cooling_delta_T(op.lam, params)

    mbt = mbt_spark_deg(op.rpm, op.p_im_pa, params)
    kls, unavoidable = knock_limited_spark(
        op.rpm, t_knock, m_air_cyl, m_fuel_burn_cyl, op.octane, params
    )

    spark = min(mbt, kls) if spark_deg is None else spark_deg
    knock_limited = (kls < mbt) and (spark >= kls - 1e-6)

    integral = knock_integral(op.rpm, t_knock, m_air_cyl, m_fuel_burn_cyl, spark, op.octane, params)
    torque, p_brake = brake_torque_power(op.rpm, m_dot_fuel_burn, spark, mbt, params)

    # crude EGT estimate (approximate; calibrated later)
    retard = max(0.0, mbt - spark)
    boost_bar = (op.p_im_pa - P_ATM) / 1e5
    egt_c = 650.0 + 12.0 * retard + 220.0 * (op.lam - 0.80) + 40.0 * boost_bar

    return MvemResult(
        rpm=op.rpm,
        eta_vol=eta_vol,
        m_dot_air=m_dot_air,
        m_dot_fuel=m_dot_fuel,
        afr=afr_from_lambda(op.lam, params),
        mbt_deg=mbt,
        knock_limited_deg=kls,
        spark_deg=spark,
        knock_limited=knock_limited,
        knock_unavoidable=unavoidable,
        knock_margin=max(0.0, 1.0 - integral),
        torque_nm=torque,
        power_kw=p_brake / 1000.0,
        power_hp=p_brake / WATT_PER_HP,
        egt_c=egt_c,
    )
