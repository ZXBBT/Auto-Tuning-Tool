"""Differentiable (numpy v0) mean-value engine model — the physics core (M2)."""

from .mvem import OperatingPoint, MvemResult, simulate_wot

__all__ = ["OperatingPoint", "MvemResult", "simulate_wot"]
