"""Glue between the HTTP layer and the library: run a pipeline stage, return plain
JSON-safe dicts. Kept free of FastAPI so it is unit-testable on its own."""

from __future__ import annotations

import io
import math
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from ..config import EA888_GEN3
from ..data import COBB_EA888, detect_wot_segments, generate_cobb_wot_log, ingest_dataframe, qa_report
from ..data.schema import LogFrame
from ..diagnostics import diagnose
from ..model import data as domain
from ..model.data import FEATURES, TARGETS
from ..optimize import SafetyLimits, optimize_sweep
from ..physics import OperatingPoint, simulate_wot
from ..physics.constants import P_ATM, WATT_PER_HP

CAVEAT = (
    "All model outputs come from an uncalibrated physics simulator and a neural surrogate "
    "trained on it. They demonstrate the method, not a real-world tune. Never flash these numbers."
)

# channels plotted in the log view (whichever are present)
PLOT_CHANNELS = [
    "time_s", "rpm", "boost_kpa", "map_kpa", "lambda", "lambda_target", "ignition_deg",
    "knock_retard_cyl1", "knock_retard_cyl2", "knock_retard_cyl3", "knock_retard_cyl4",
    "charge_temp_c", "pedal_pct",
]
MAX_PLOT_POINTS = 1500
BASELINE = (12.0, 1.0, 0.92)  # (spark_deg, boost_bar, lambda) reference for the gain figure

SAMPLES = {
    "conservative": {"title": "Conservative tune", "detail": "timing 4 deg below the knock limit", "spark_offset_deg": -4.0, "seed": 3},
    "near-limit": {"title": "Near the knock limit", "detail": "best-safe timing; occasional knock retard", "spark_offset_deg": 0.0, "seed": 0},
}


class InputError(ValueError):
    """The request's data is unusable (bad CSV, missing channels, ...)."""


def clean(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalars and NaN/inf into strict-JSON values."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    return obj


# ------------------------------- logs -------------------------------
def sample_log(sample_id: str) -> LogFrame:
    spec = SAMPLES[sample_id]
    raw = generate_cobb_wot_log(spark_offset_deg=spec["spark_offset_deg"], seed=spec["seed"])
    return ingest_dataframe(raw, profile=COBB_EA888, meta={"source_path": f"sample:{sample_id}"})


def parse_upload(content: bytes, filename: str, max_rows: int = 200_000) -> LogFrame:
    try:
        raw = pd.read_csv(io.BytesIO(content), nrows=max_rows + 1)
    except Exception as e:  # pandas raises a zoo of parser errors
        raise InputError(f"could not parse CSV: {e}") from e
    if len(raw) > max_rows:
        raise InputError(f"log too long (> {max_rows} rows)")
    lf = ingest_dataframe(raw, profile=COBB_EA888, meta={"source_path": filename})
    if lf.missing:
        raise InputError(
            f"missing required channels {lf.missing}; recognised columns: {sorted(lf.df.columns)}"
        )
    return lf


def _downsample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if len(df) <= n:
        return df
    idx = np.linspace(0, len(df) - 1, n).round().astype(int)
    return df.iloc[np.unique(idx)]


def analyze_log(lf: LogFrame, octane: float = 98.0) -> dict:
    df = lf.df
    report = diagnose(lf, octane=octane)
    segs = detect_wot_segments(df)
    wot = None
    if segs and "time_s" in df.columns:
        a, b = max(segs, key=lambda s: s[1] - s[0])
        wot = {"t_start": df["time_s"].iloc[a], "t_end": df["time_s"].iloc[b]}
    plot = _downsample(df[[c for c in PLOT_CHANNELS if c in df.columns]], MAX_PLOT_POINTS)
    return clean(
        {
            "source": lf.meta.get("source_path"),
            "qa": qa_report(lf),
            "wot": wot,
            "wot_rpm": report.wot_rpm,
            "findings": [asdict(f) for f in report.findings],
            "est_power_left_hp": report.est_power_left_hp,
            "report_text": report.render(),
            "series": {c: plot[c].to_numpy() for c in plot.columns},
            "caveat": CAVEAT,
        }
    )


# ---------------------------- explorer ----------------------------
def _features(rpm, boost_bar, lam, spark_deg, charge_temp_c, octane) -> pd.DataFrame:
    spark = np.atleast_1d(np.asarray(spark_deg, dtype=float))
    n = len(spark)
    return pd.DataFrame(
        {
            "rpm": np.full(n, rpm),
            "p_im_pa": np.full(n, P_ATM + boost_bar * 1e5),
            "charge_temp_k": np.full(n, charge_temp_c + 273.15),
            "lam": np.full(n, lam),
            "octane": np.full(n, octane),
            "spark_deg": spark,
        }
    )[FEATURES]


def predict_point(ensemble, rpm, boost_bar, lam, spark_deg, charge_temp_c, octane, sweep_n: int = 43) -> dict:
    """Surrogate (mean +/- sigma) and physics model at one point, plus a spark sweep."""
    tq, km = TARGETS.index("torque_nm"), TARGETS.index("knock_margin")
    omega = 2.0 * math.pi * rpm / 60.0

    mean, std = ensemble.predict(_features(rpm, boost_bar, lam, spark_deg, charge_temp_c, octane))
    op = OperatingPoint(rpm, P_ATM + boost_bar * 1e5, charge_temp_c + 273.15, lam, octane)
    phys = simulate_wot(op, EA888_GEN3, spark_deg=spark_deg)

    sparks = np.linspace(*domain.SPARK, sweep_n)
    s_mean, s_std = ensemble.predict(_features(rpm, boost_bar, lam, sparks, charge_temp_c, octane))
    phys_sweep = [simulate_wot(op, EA888_GEN3, spark_deg=float(s)) for s in sparks]

    return clean(
        {
            "surrogate": {
                "torque_nm": mean[0, tq],
                "torque_sigma": std[0, tq],
                "power_hp": mean[0, tq] * omega / WATT_PER_HP,
                "knock_margin": mean[0, km],
                "knock_margin_sigma": std[0, km],
            },
            "physics": {
                "torque_nm": phys.torque_nm,
                "power_hp": phys.power_hp,
                "knock_margin": phys.knock_margin,
                "mbt_deg": phys.mbt_deg,
                "knock_limited_deg": phys.knock_limited_deg,
                "egt_c": phys.egt_c,
                "afr": phys.afr,
            },
            "sweep": {
                "spark_deg": sparks,
                "torque_mean": s_mean[:, tq],
                "torque_sigma": s_std[:, tq],
                "knock_margin_mean": s_mean[:, km],
                "knock_margin_sigma": s_std[:, km],
                "physics_torque": [r.torque_nm for r in phys_sweep],
                "physics_knock_margin": [r.knock_margin for r in phys_sweep],
            },
        }
    )


# ---------------------------- optimizer ----------------------------
def run_optimize(ensemble, params: dict, progress=None) -> dict:
    limits = SafetyLimits(
        knock_margin_min=params["knock_margin_min"],
        boost_max_bar=params["boost_max_bar"],
        lam_min=params["lam_min"],
        sigma_k=params["sigma_k"],
    )
    rpms = list(range(int(params["rpm_start"]), int(params["rpm_end"]) + 1, int(params["rpm_step"])))
    res = optimize_sweep(
        ensemble, rpms, charge_temp_c=params["charge_temp_c"], octane=params["octane"],
        limits=limits, baseline=BASELINE, progress=progress,
    )
    # the table holds float32 (from torch); widen + re-round so JSON shows 1.79, not 1.7899999
    table = res.table.astype({c: "float64" for c in res.table.select_dtypes("float32").columns}).round(3)
    return clean(
        {
            "rows": table.to_dict(orient="records"),
            "baseline_power_hp": res.baseline_power_hp,
            "baseline": dict(zip(("spark_deg", "boost_bar", "lambda"), BASELINE)),
            "peak_power_hp": res.peak_power_hp,
            "baseline_peak_hp": res.baseline_peak_hp,
            "gain_hp": res.gain_hp,
            "limits": asdict(limits),
            "params": params,
            "caveat": CAVEAT,
        }
    )


def model_domain() -> dict:
    """The surrogate's training domain: inputs outside it are extrapolation."""
    return {
        "rpm": domain.RPM,
        "boost_bar": domain.BOOST_BAR,
        "charge_temp_c": domain.CHARGE_C,
        "lambda": domain.LAM,
        "octane": domain.OCTANE,
        "spark_deg": domain.SPARK,
    }
