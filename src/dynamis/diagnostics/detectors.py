"""Individual bottleneck detectors operating on a WOT-segment DataFrame."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..calibration.predict import predict_cheap, predict_knock_limited_deg
from ..config.engine import EngineParams
from ..physics.combustion import mbt_spark_deg
from ..physics.constants import WATT_PER_HP

_CYL = ["knock_retard_cyl1", "knock_retard_cyl2", "knock_retard_cyl3", "knock_retard_cyl4"]


@dataclass
class Finding:
    category: str       # knock | fueling | boost | timing | general
    severity: str       # info | low | medium | high
    message: str
    rpm_range: tuple | None = None
    source: str = "observed"   # observed | model-estimated


# ----------------------------- observed -----------------------------
def detect_knock(df: pd.DataFrame, thresh: float = 0.5) -> list[Finding]:
    if "knock_retard_deg" not in df.columns:
        return [Finding("knock", "info", "no knock-retard channel logged")]
    kr = df["knock_retard_deg"].to_numpy()
    rpm = df["rpm"].to_numpy()
    mask = kr > thresh
    if not mask.any():
        return [Finding("knock", "info", f"no significant knock retard (> {thresh:.1f} deg) logged")]
    mx = float(kr[mask].max())
    sev = "high" if mx >= 3.0 else "medium" if mx >= 1.5 else "low"
    worst = ""
    cyls = [c for c in _CYL if c in df.columns]
    if cyls:
        wc = max(cyls, key=lambda c: float(df[c].max()))
        worst = f"; worst {wc.replace('knock_retard_', '')}"
    return [
        Finding(
            "knock",
            sev,
            f"knock retard active {int(rpm[mask].min())}-{int(rpm[mask].max())} rpm "
            f"(max {mx:.1f} deg, {int(mask.sum())} samples){worst}",
            (float(rpm[mask].min()), float(rpm[mask].max())),
            "observed",
        )
    ]


def detect_fueling(df: pd.DataFrame, lean_tol: float = 0.04, rich_tol: float = 0.06) -> list[Finding]:
    if "lambda" not in df.columns or "lambda_target" not in df.columns:
        return [Finding("fueling", "info", "lambda or lambda_target channel missing")]
    rpm = df["rpm"].to_numpy()
    dev = (df["lambda"] - df["lambda_target"]).to_numpy()
    out: list[Finding] = []
    lean = dev > lean_tol
    if lean.any():
        out.append(
            Finding(
                "fueling",
                "high",
                f"LEAN of target by up to {dev[lean].max():.2f} lambda "
                f"{int(rpm[lean].min())}-{int(rpm[lean].max())} rpm (fuel-delivery / safety risk)",
                (float(rpm[lean].min()), float(rpm[lean].max())),
                "observed",
            )
        )
    rich = dev < -rich_tol
    if rich.any():
        out.append(
            Finding(
                "fueling",
                "low",
                f"richer than target by up to {(-dev[rich]).max():.2f} lambda "
                f"{int(rpm[rich].min())}-{int(rpm[rich].max())} rpm (fueling inefficiency)",
                (float(rpm[rich].min()), float(rpm[rich].max())),
                "observed",
            )
        )
    if not out:
        out.append(Finding("fueling", "info", f"AFR tracks target (max dev {np.abs(dev).max():.2f} lambda)"))
    return out


def detect_boost(df: pd.DataFrame, droop_frac: float = 0.08) -> list[Finding]:
    if "boost_kpa" not in df.columns:
        return [Finding("boost", "info", "no boost channel logged")]
    rpm = df["rpm"].to_numpy()
    boost = df["boost_kpa"].to_numpy()
    peak = float(boost.max())
    rpm_peak = float(rpm[boost.argmax()])
    end = float(boost[rpm.argmax()])
    out = [Finding("boost", "info", f"peak boost {peak / 100.0:.2f} bar ({peak:.0f} kPa) at {int(rpm_peak)} rpm", source="observed")]
    droop = (peak - end) / peak if peak > 0 else 0.0
    if droop > droop_frac:
        out.append(
            Finding(
                "boost",
                "low",
                f"top-end boost droop {droop * 100:.0f}% (peak {peak:.0f} -> {end:.0f} kPa by redline)",
                (rpm_peak, float(rpm.max())),
                "observed",
            )
        )
    return out


# -------------------------- model-estimated --------------------------
def estimate_timing_headroom(
    df: pd.DataFrame, engine: EngineParams, octane: float = 98.0, rpm_bin: float = 400.0
) -> tuple[list[Finding], float]:
    need = ["rpm", "map_kpa", "charge_temp_c", "lambda", "ignition_deg"]
    if not all(c in df.columns for c in need):
        return [Finding("timing", "info", "insufficient channels for timing-headroom estimate", source="model-estimated")], 0.0

    seg = df.copy()
    seg["_bin"] = (seg["rpm"] // rpm_bin) * rpm_bin
    best_power, log_power, headroom, pos_bins = [], [], [], []
    for _, g in seg.groupby("_bin"):
        rpm_b = float(g["rpm"].median())
        p_im = float(g["map_kpa"].median()) * 1000.0  # kPa -> Pa
        t_k = float(g["charge_temp_c"].median()) + 273.15
        lam = float(g["lambda"].median())
        spark_log = float(g["ignition_deg"].median())

        kls = predict_knock_limited_deg(engine, rpm_b, p_im, t_k, lam, octane)
        best = min(mbt_spark_deg(rpm_b, p_im, engine), kls)
        hr = best - spark_log
        tq_log = predict_cheap(engine, rpm_b, p_im, t_k, lam, octane, spark_log)["torque_nm"]
        tq_best = predict_cheap(engine, rpm_b, p_im, t_k, lam, octane, max(spark_log, best))["torque_nm"]
        omega = 2.0 * np.pi * rpm_b / 60.0
        best_power.append(tq_best * omega / WATT_PER_HP)
        log_power.append(tq_log * omega / WATT_PER_HP)
        headroom.append(hr)
        if hr > 1.5:
            pos_bins.append(rpm_b)

    est_left = max(0.0, (max(best_power) - max(log_power)) if best_power else 0.0)
    med_hr = float(np.median(headroom)) if headroom else 0.0
    if est_left > 3.0 and med_hr > 1.0:
        rr = (min(pos_bins), max(pos_bins)) if pos_bins else None
        return [
            Finding(
                "timing",
                "medium",
                f"ignition ~{med_hr:.1f} deg below the knock limit (median) -> "
                f"~{est_left:.0f} hp estimated available at current boost",
                rr,
                "model-estimated",
            )
        ], est_left
    return [Finding("timing", "info", "ignition at/near the knock limit; little timing headroom at current boost", source="model-estimated")], est_left
