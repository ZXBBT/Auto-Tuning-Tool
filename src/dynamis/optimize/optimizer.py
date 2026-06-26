"""Gradient-based constrained optimizer over the differentiable surrogate.

Each WOT operating point (one RPM) is independent, so we optimize the whole RPM sweep as
one batch: free variables (boost, lambda, spark) per point are reparameterized through a
sigmoid into their box limits (so box constraints hold exactly), and we maximize torque
minus a penalty on the (sigma-aware) knock-margin constraint. Backprop flows through the
surrogate to the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch

from ..model.data import TARGETS
from ..physics.constants import P_ATM, WATT_PER_HP
from .constraints import SafetyLimits


@dataclass
class TuneResult:
    table: pd.DataFrame          # per-rpm recommended calibration + predictions
    peak_power_hp: float
    baseline_peak_hp: float
    gain_hp: float


def _power_hp(torque_nm: np.ndarray, rpm: np.ndarray) -> np.ndarray:
    return torque_nm * (2.0 * np.pi * rpm / 60.0) / WATT_PER_HP


def _active_constraint(boost, lam, spark, margin, limits: SafetyLimits) -> str:
    if margin <= limits.knock_margin_min + 0.03:
        return "knock"
    if boost >= limits.boost_max_bar - 0.03:
        return "boost ceiling"
    if spark >= limits.spark_max - 0.3:
        return "spark authority"
    if lam <= limits.lam_min + 0.01:
        return "lambda (rich) limit"
    return "open"


def optimize_sweep(
    ensemble,
    rpms,
    charge_temp_c: float = 50.0,
    octane: float = 98.0,
    limits: SafetyLimits | None = None,
    steps: int = 600,
    lr: float = 0.05,
    baseline=(12.0, 1.0, 0.92),  # (spark_deg, boost_bar, lambda) reference calibration
) -> TuneResult:
    limits = limits or SafetyLimits()
    dev = ensemble.members[0].device
    rpms = np.asarray(rpms, dtype=float)
    n = len(rpms)

    rpm_t = torch.tensor(rpms, dtype=torch.float32, device=dev)
    charge_k = torch.full((n,), charge_temp_c + 273.15, device=dev)
    oct_t = torch.full((n,), float(octane), device=dev)
    lo = torch.tensor([limits.boost_min_bar, limits.lam_min, limits.spark_min], device=dev)
    hi = torch.tensor([limits.boost_max_bar, limits.lam_max, limits.spark_max], device=dev)

    tq_i, km_i = TARGETS.index("torque_nm"), TARGETS.index("knock_margin")

    def features(dec):  # dec: (n, 3) -> (n, n_features) in FEATURES order
        boost, lam, spark = dec[:, 0], dec[:, 1], dec[:, 2]
        p_im = P_ATM + boost * 1e5
        return torch.stack([rpm_t, p_im, charge_k, lam, oct_t, spark], dim=1)

    theta = torch.zeros(n, 3, device=dev, requires_grad=True)
    opt = torch.optim.Adam([theta], lr=lr)
    for _ in range(steps):
        opt.zero_grad()
        dec = lo + (hi - lo) * torch.sigmoid(theta)
        mean, std = ensemble.forward_tensor(features(dec))
        torque, margin, sig = mean[:, tq_i], mean[:, km_i], std[:, km_i]
        margin_eff = margin - limits.sigma_k * sig
        penalty = torch.relu(limits.knock_margin_min - margin_eff)
        # linear + quadratic: the linear term keeps a constant restoring gradient at the
        # boundary (a pure quadratic penalty's gradient vanishes there and under-enforces).
        loss = (-torque / 100.0 + 8.0 * penalty + 80.0 * penalty.pow(2)).mean()
        loss.backward()
        opt.step()

    with torch.no_grad():
        dec = lo + (hi - lo) * torch.sigmoid(theta)
        mean, std = ensemble.forward_tensor(features(dec))
    dec_np = dec.cpu().numpy()
    boost_bar, lam, spark = dec_np[:, 0], dec_np[:, 1], dec_np[:, 2]
    torque = mean[:, tq_i].cpu().numpy()
    margin = mean[:, km_i].cpu().numpy()
    sig_tq = std[:, tq_i].cpu().numpy()
    power = _power_hp(torque, rpms)

    active = [_active_constraint(boost_bar[i], lam[i], spark[i], margin[i], limits) for i in range(n)]
    table = pd.DataFrame(
        {
            "rpm": rpms.astype(int),
            "boost_bar": np.round(boost_bar, 2),
            "lambda": np.round(lam, 3),
            "spark_deg": np.round(spark, 1),
            "torque_nm": np.round(torque, 0),
            "power_hp": np.round(power, 0),
            "knock_margin": np.round(margin, 3),
            "sigma_torque": np.round(sig_tq, 1),
            "active_limit": active,
        }
    )

    # baseline reference (fixed conservative calibration) for the gain report
    b_spark, b_boost, b_lam = baseline
    base_dec = torch.tensor(np.tile([b_boost, b_lam, b_spark], (n, 1)), dtype=torch.float32, device=dev)
    with torch.no_grad():
        base_mean, _ = ensemble.forward_tensor(features(base_dec))
    base_power = _power_hp(base_mean[:, tq_i].cpu().numpy(), rpms)

    peak = float(power.max())
    base_peak = float(base_power.max())
    return TuneResult(table=table, peak_power_hp=peak, baseline_peak_hp=base_peak, gain_hp=peak - base_peak)
