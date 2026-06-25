"""Volumetric efficiency model.

v0: a smooth RPM-dependent hump. This is a placeholder shape; `eta_vol(N, p_im)` is a
prime target of the M3 calibration against real `Air Mass per stroke` log channel.
"""

from __future__ import annotations

import math

from ..config.engine import EngineParams


def volumetric_efficiency(rpm: float, p_im_pa: float, params: EngineParams) -> float:
    shape = math.exp(-0.5 * ((rpm - params.ve_rpm_peak) / params.ve_rpm_width) ** 2)
    return params.ve_floor + (params.ve_peak - params.ve_floor) * shape
