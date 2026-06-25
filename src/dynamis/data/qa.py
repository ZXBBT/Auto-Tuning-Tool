"""Quality assurance: WOT-pull detection, range checks, summary report."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import REQUIRED_KEYS, LogFrame

# plausible physical ranges for canonical channels (for outlier flagging)
_RANGES = {
    "rpm": (0.0, 8500.0),
    "map_kpa": (20.0, 350.0),
    "boost_kpa": (-100.0, 260.0),
    "lambda": (0.6, 1.4),
    "lambda_target": (0.6, 1.4),
    "ignition_deg": (-15.0, 45.0),
    "iat_c": (-25.0, 95.0),
    "charge_temp_c": (-25.0, 130.0),
    "knock_retard_deg": (0.0, 25.0),
    "pedal_pct": (0.0, 100.5),
}


def detect_wot_segments(
    df: pd.DataFrame, pedal_thresh: float = 95.0, min_samples: int = 10, min_rpm_rise: float = 1500.0
) -> list[tuple[int, int]]:
    """Return [(start, end)] index spans that look like wide-open-throttle pulls.

    A pull = pedal at/near floor for a sustained run whose RPM rises substantially.
    Falls back to an RPM-rise heuristic if no pedal channel is present.
    """
    n = len(df)
    if n == 0:
        return []
    if "pedal_pct" in df.columns:
        mask = (df["pedal_pct"] >= pedal_thresh).to_numpy()
    elif "rpm" in df.columns:
        mask = np.r_[True, np.diff(df["rpm"].to_numpy()) > 0]
    else:
        return []

    segments: list[tuple[int, int]] = []
    start = None
    for i in range(n):
        if mask[i] and start is None:
            start = i
        elif not mask[i] and start is not None:
            segments.append((start, i - 1))
            start = None
    if start is not None:
        segments.append((start, n - 1))

    out = []
    rpm = df["rpm"].to_numpy() if "rpm" in df.columns else None
    for a, b in segments:
        if b - a + 1 < min_samples:
            continue
        if rpm is not None and (rpm[b] - rpm[a]) < min_rpm_rise:
            continue
        out.append((a, b))
    return out


def range_violations(df: pd.DataFrame) -> dict[str, int]:
    viol: dict[str, int] = {}
    for col, (lo, hi) in _RANGES.items():
        if col in df.columns:
            s = df[col]
            n_bad = int(((s < lo) | (s > hi)).sum())
            if n_bad:
                viol[col] = n_bad
    return viol


def qa_report(lf: LogFrame) -> dict:
    df = lf.df
    n = len(df)
    duration = float(df["time_s"].iloc[-1] - df["time_s"].iloc[0]) if "time_s" in df and n > 1 else 0.0
    rate = (n - 1) / duration if duration > 0 else float("nan")
    wot = detect_wot_segments(df)
    wot_rpm = None
    if wot and "rpm" in df.columns:
        a, b = wot[0]
        wot_rpm = (float(df["rpm"].iloc[a]), float(df["rpm"].iloc[b]))
    return {
        "rows": n,
        "duration_s": round(duration, 2),
        "sample_rate_hz": round(rate, 1) if rate == rate else None,
        "channels_present": sorted(df.columns),
        "channels_missing_required": sorted(REQUIRED_KEYS - set(df.columns)),
        "wot_segments": len(wot),
        "first_wot_rpm_span": wot_rpm,
        "range_violations": range_violations(df),
    }
