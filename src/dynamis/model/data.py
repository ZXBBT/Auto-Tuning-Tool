"""Training data for the surrogate (torch-free).

Samples operating points + calibration over their ranges and labels them with the MVEM
(torque + knock margin). Uses the fast physics paths so dataset generation is cheap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..calibration.predict import predict_cheap
from ..config import EA888_GEN3
from ..config.engine import EngineParams
from ..physics.airpath import air_mass_flow
from ..physics.constants import N_REV_PER_CYCLE, P_ATM
from ..physics.fueling import charge_cooling_delta_T, fuel_mass_flow
from ..physics.knock import knock_integral
from ..physics.volumetric import volumetric_efficiency

FEATURES = ["rpm", "p_im_pa", "charge_temp_k", "lam", "octane", "spark_deg"]
TARGETS = ["torque_nm", "knock_margin"]

# sampling ranges (training domain)
RPM = (2500.0, 7000.0)
BOOST_BAR = (0.3, 2.0)
CHARGE_C = (30.0, 70.0)
LAM = (0.78, 1.0)
OCTANE = (91.0, 104.0)
SPARK = (5.0, 26.0)


class Standardizer:
    """Zero-mean, unit-variance feature/target scaling."""

    def __init__(self):
        self.mean = None
        self.std = None

    def fit(self, x: np.ndarray) -> "Standardizer":
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0) + 1e-8
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse(self, x: np.ndarray) -> np.ndarray:
        return x * self.std + self.mean

    def fit_transform(self, x: np.ndarray) -> np.ndarray:
        return self.fit(x).transform(x)


def sample_inputs(n: int, seed: int = 0, boost_bar=BOOST_BAR) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    boost = rng.uniform(*boost_bar, n)
    return pd.DataFrame(
        {
            "rpm": rng.uniform(*RPM, n),
            "p_im_pa": P_ATM + boost * 1e5,
            "charge_temp_k": rng.uniform(*CHARGE_C, n) + 273.15,
            "lam": rng.uniform(*LAM, n),
            "octane": rng.uniform(*OCTANE, n),
            "spark_deg": rng.uniform(*SPARK, n),
        }
    )


def _knock_margin(eng: EngineParams, rpm, p_im, t_c, lam, octane, spark) -> float:
    t_knock = t_c - charge_cooling_delta_T(lam, eng)
    eta_vol = volumetric_efficiency(rpm, p_im, eng)
    m_dot_air = air_mass_flow(rpm, p_im, t_c, eta_vol, eng)
    cps = (rpm / 60.0) / N_REV_PER_CYCLE
    m_air_cyl = m_dot_air / cps / eng.num_cylinders
    m_dot_fuel = fuel_mass_flow(m_dot_air, lam, eng)
    m_fuel_burn_cyl = min(m_dot_fuel, m_dot_air / eng.afr_stoich) / cps / eng.num_cylinders
    integral = knock_integral(rpm, t_knock, m_air_cyl, m_fuel_burn_cyl, spark, octane, eng)
    return max(0.0, 1.0 - integral)


def simulate_targets(df: pd.DataFrame, engine: EngineParams = EA888_GEN3) -> pd.DataFrame:
    out = df.copy()
    torque, margin = [], []
    for r in df.itertuples():
        torque.append(predict_cheap(engine, r.rpm, r.p_im_pa, r.charge_temp_k, r.lam, r.octane, r.spark_deg)["torque_nm"])
        margin.append(_knock_margin(engine, r.rpm, r.p_im_pa, r.charge_temp_k, r.lam, r.octane, r.spark_deg))
    out["torque_nm"] = torque
    out["knock_margin"] = margin
    return out


def make_dataset(n: int = 2000, seed: int = 0, engine: EngineParams = EA888_GEN3) -> pd.DataFrame:
    return simulate_targets(sample_inputs(n, seed), engine)
