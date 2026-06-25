"""Least-squares calibration of theta_phys to a labeled dataset."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from ..config.engine import EngineParams
from .predict import CHEAP_TARGETS, predict_cheap, predict_knock_limited_deg


def _predict_one(eng: EngineParams, row, target: str) -> float:
    if target in CHEAP_TARGETS:
        return predict_cheap(eng, row.rpm, row.p_im_pa, row.charge_temp_k, row.lam, row.octane, row.spark_deg)[target]
    if target == "knock_limited_deg":
        return predict_knock_limited_deg(eng, row.rpm, row.p_im_pa, row.charge_temp_k, row.lam, row.octane)
    raise ValueError(f"unknown target: {target}")


def predict_targets(eng: EngineParams, df: pd.DataFrame, targets: list[str]) -> dict[str, np.ndarray]:
    return {t: np.array([_predict_one(eng, row, t) for row in df.itertuples()]) for t in targets}


@dataclass
class CalibrationResult:
    fitted: dict[str, float]
    rmse: dict[str, float]
    success: bool
    cost: float


def calibrate(
    df: pd.DataFrame,
    engine: EngineParams,
    free_params: list[str],
    targets: list[str],
    init: list[float],
    bounds: list[tuple[float, float]],
    diff_step: float | None = 1e-3,
) -> CalibrationResult:
    """Fit `free_params` of `engine` so model `targets` match the observed columns in `df`.

    `diff_step` is the *relative* finite-difference step. The default (1e-3) is larger
    than scipy's default because some targets (e.g. knock-limited spark) come from a
    binary search and are quantized — too small a step yields a zero gradient.
    """
    obs = {t: df[t].to_numpy(dtype=float) for t in targets}
    scale = {t: (np.std(obs[t]) or 1.0) for t in targets}

    def residuals(x: np.ndarray) -> np.ndarray:
        cand = replace(engine, **dict(zip(free_params, x)))
        preds = predict_targets(cand, df, targets)
        return np.concatenate([(preds[t] - obs[t]) / scale[t] for t in targets])

    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    sol = least_squares(
        residuals, np.array(init, dtype=float), bounds=(lo, hi), x_scale="jac", diff_step=diff_step
    )

    fitted = dict(zip(free_params, sol.x))
    cand = replace(engine, **fitted)
    preds = predict_targets(cand, df, targets)
    rmse = {t: float(np.sqrt(np.mean((preds[t] - obs[t]) ** 2))) for t in targets}
    return CalibrationResult(fitted=fitted, rmse=rmse, success=bool(sol.success), cost=float(sol.cost))
