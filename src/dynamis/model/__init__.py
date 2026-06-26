"""Surrogate forward model + uncertainty (M4).

A fast NN emulator of the MVEM: perf = f(operating point, calibration). Trained on sim
data; a deep ensemble provides predictive uncertainty (sigma) so low-confidence regions
can be flagged. The surrogate is what later lets the optimizer search quickly (M6).

`model.data` is torch-free; `surrogate`/`ensemble` require PyTorch.
"""

from .data import FEATURES, TARGETS, Standardizer, make_dataset, sample_inputs, simulate_targets

__all__ = [
    "FEATURES",
    "TARGETS",
    "Standardizer",
    "make_dataset",
    "sample_inputs",
    "simulate_targets",
]

try:  # torch-dependent pieces are optional at import time
    from .ensemble import DeepEnsemble
    from .surrogate import Surrogate

    __all__ += ["Surrogate", "DeepEnsemble"]
except ModuleNotFoundError:  # pragma: no cover - torch not installed
    pass
