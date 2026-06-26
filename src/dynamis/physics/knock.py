"""Knock — Livengood-Wu autoignition integral with a Douaud-Eyzat ignition delay.

This module is the physical heart of "ignition timing pull". A single-zone closed-cycle
model gives the in-cylinder pressure trace; the unburned end-gas temperature follows the
pressure isentropically; the Livengood-Wu integral accumulates autoignition reaction
progress. Knock is predicted when the integral reaches 1 before combustion completes.

Correct, testable trends (see tests / sanity script):
  more boost / higher IAT / more spark advance  -> more knock
  higher octane / richer mixture (charge cooling) -> less knock
"""

from __future__ import annotations

import math

import numpy as np

from ..config.engine import EngineParams
from .constants import CV_CHARGE, P_ATM, R_AIR


def cylinder_volume(theta_deg: np.ndarray, params: EngineParams) -> np.ndarray:
    """Slider-crank cylinder volume [m^3] at crank angle theta [deg ATDC firing]."""
    th = np.radians(theta_deg)
    r = params.crank_radius_m
    rod = params.conrod_m
    x = r * (1.0 - np.cos(th)) + rod * (1.0 - np.sqrt(1.0 - (r / rod) ** 2 * np.sin(th) ** 2))
    return params.clearance_volume_m3 + params.piston_area_m2 * x


def wiebe(theta_deg: np.ndarray, soc_deg: float, params: EngineParams) -> np.ndarray:
    """Wiebe mass-fraction-burned from start-of-combustion `soc_deg`."""
    frac = (theta_deg - soc_deg) / params.burn_duration_deg
    frac = np.clip(frac, 0.0, None)
    xb = 1.0 - np.exp(-params.wiebe_a * frac ** (params.wiebe_m + 1.0))
    return np.clip(xb, 0.0, 1.0)


def knock_integral(
    rpm: float,
    T_charge_k: float,
    m_air_cyl: float,
    m_fuel_cyl: float,
    spark_btdc: float,
    octane: float,
    params: EngineParams,
    n_steps: int = 240,
) -> float:
    """Livengood-Wu autoignition integral over the closed cycle. Knock if >= 1."""
    theta = np.linspace(params.ivc_atdc_deg, 80.0, n_steps)
    vol = cylinder_volume(theta, params)
    soc = -spark_btdc  # start of combustion at spark, deg ATDC
    xb = wiebe(theta, soc, params)

    m = m_air_cyl + m_fuel_cyl
    q_total = m_fuel_cyl * params.fuel_lhv * params.eta_combustion

    temp = T_charge_k
    p = m * R_AIR * temp / vol[0]
    p_ivc = p
    gu = params.gamma_unburned
    deg_per_s = 6.0 * rpm  # 360 deg/rev * rpm/60

    integral = 0.0
    for i in range(1, n_steps):
        d_vol = vol[i] - vol[i - 1]
        d_xb = xb[i] - xb[i - 1]
        d_q = q_total * d_xb
        temp += (d_q - p * d_vol) / (m * CV_CHARGE)
        p = m * R_AIR * temp / vol[i]

        # unburned end-gas temperature via isentropic compression by cylinder pressure
        t_u = T_charge_k * (p / p_ivc) ** ((gu - 1.0) / gu)
        p_atm = p / P_ATM
        # Douaud-Eyzat ignition delay [ms] -> [s]
        tau_s = 1e-3 * (
            params.knock_A
            * (octane / 100.0) ** params.knock_a_on
            * p_atm ** (-params.knock_n_p)
            * math.exp(params.knock_B / max(t_u, 300.0))
        )
        dt = (theta[i] - theta[i - 1]) / deg_per_s
        integral += dt / tau_s * (1.0 - xb[i])  # only unburned charge can autoignite
        if integral >= 1.0:
            break
    return integral


def knock_limited_spark(
    rpm: float,
    T_charge_k: float,
    m_air_cyl: float,
    m_fuel_cyl: float,
    octane: float,
    params: EngineParams,
    spark_lo: float = 2.0,
    spark_hi: float = 32.0,
    target: float = 1.0,
    iters: int = 18,
) -> tuple[float, bool]:
    """Max spark advance [deg BTDC] keeping knock integral <= target.

    Returns (knock_limited_spark, unavoidable) where `unavoidable` is True if even the
    minimum spark still knocks (a mechanical/fuel red flag).
    """

    def integral(s: float) -> float:
        return knock_integral(rpm, T_charge_k, m_air_cyl, m_fuel_cyl, s, octane, params)

    if integral(spark_lo) > target:
        return spark_lo, True
    if integral(spark_hi) <= target:
        return spark_hi, False

    lo, hi = spark_lo, spark_hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if integral(mid) <= target:
            lo = mid
        else:
            hi = mid
    return lo, False
