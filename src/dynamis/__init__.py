"""Dynamis — physics-informed ECU calibration analysis & optimization.

See docs/ARCHITECTURE.md for the overall design. This package currently implements
the v0 steady-state mean-value engine model (MVEM) used as the differentiable physics
core (M2). It is written in numpy for clarity; the pure-function structure is intended
to port to an autodiff backend (PyTorch) when calibration/optimization need gradients.
"""

__version__ = "0.0.1"
