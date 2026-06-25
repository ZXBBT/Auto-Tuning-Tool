"""Calibration (M3): fit physics parameters (theta_phys) to data.

On sim data this is a parameter-recovery / identifiability exercise (the fit should
recover known injected params). On real logs it anchors the model to reality. Uses
scipy least-squares — no autodiff needed for the parametric fit.
"""

from .dataset import label_dataset, make_grid
from .fit import calibrate, predict_targets

__all__ = ["make_grid", "label_dataset", "calibrate", "predict_targets"]
