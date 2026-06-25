"""Build labeled training datasets from the sim (a grid of WOT operating points)."""

from __future__ import annotations

from itertools import product

import pandas as pd

from ..config.engine import EngineParams
from ..physics.constants import P_ATM
from .fit import predict_targets


def make_grid(
    rpms=(3000, 3800, 4600, 5400, 6200, 6800),
    boosts_bar=(0.6, 1.0, 1.4, 1.8),
    charge_c=(40.0, 55.0),
    lam: float = 0.85,
    octane: float = 98.0,
    spark_deg: float = 15.0,
) -> pd.DataFrame:
    rows = [
        {
            "rpm": float(r),
            "p_im_pa": P_ATM + b * 1e5,
            "charge_temp_k": tc + 273.15,
            "lam": lam,
            "octane": octane,
            "spark_deg": spark_deg,
        }
        for r, b, tc in product(rpms, boosts_bar, charge_c)
    ]
    return pd.DataFrame(rows)


def label_dataset(df: pd.DataFrame, engine: EngineParams, targets: list[str]) -> pd.DataFrame:
    """Add target columns by evaluating the model (the 'ground truth' for sim training)."""
    out = df.copy()
    for t, vals in predict_targets(engine, df, targets).items():
        out[t] = vals
    return out
