"""Fueling — AFR / lambda and DI charge cooling."""

from __future__ import annotations

from ..config.engine import EngineParams


def afr_from_lambda(lam: float, params: EngineParams) -> float:
    return lam * params.afr_stoich


def fuel_mass_flow(m_dot_air: float, lam: float, params: EngineParams) -> float:
    return m_dot_air / afr_from_lambda(lam, params)


def charge_cooling_delta_T(lam: float, params: EngineParams) -> float:
    """Direct-injection evaporative charge cooling [K]; richer => more cooling.

    Lowers the effective end-gas temperature, suppressing knock — the physical reason
    power tunes run rich. Magnitude is a calibratable prior.
    """
    fuel_air = 1.0 / afr_from_lambda(lam, params)
    return params.evap_cooling_k * fuel_air
