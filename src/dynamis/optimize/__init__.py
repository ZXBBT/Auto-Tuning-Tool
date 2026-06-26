"""Constrained optimizer (M6): backprop through the surrogate to find the calibration
that maximizes power within hard safety limits."""

from .constraints import SafetyLimits
from .optimizer import TuneResult, optimize_sweep

__all__ = ["SafetyLimits", "TuneResult", "optimize_sweep"]
