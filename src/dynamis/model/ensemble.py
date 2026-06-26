"""Deep ensemble of surrogates -> predictive mean + uncertainty (sigma)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from .data import FEATURES, TARGETS
from .surrogate import Surrogate


class DeepEnsemble:
    """K independently-initialized surrogates; spread of predictions = uncertainty."""

    def __init__(self, k: int = 5, features=FEATURES, targets=TARGETS, hidden=(64, 64), device=None):
        self.k = k
        self.features = list(features)
        self.targets = list(targets)
        self.hidden = hidden
        self.device = device
        self.members: list[Surrogate] = []

    def fit(self, df: pd.DataFrame, epochs: int = 500, lr: float = 1e-3) -> "DeepEnsemble":
        self.members = []
        for i in range(self.k):
            s = Surrogate(self.features, self.targets, self.hidden, self.device)
            s.fit(df, epochs=epochs, lr=lr, seed=i)
            self.members.append(s)
        return self

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Return (mean, std), each shape (n_rows, n_targets), in original units."""
        preds = np.stack([m.predict(df) for m in self.members], axis=0)  # (k, n, t)
        return preds.mean(axis=0), preds.std(axis=0)

    def forward_tensor(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Differentiable (mean, std) over members; keeps the autograd graph."""
        preds = torch.stack([m.forward_tensor(x) for m in self.members], dim=0)  # (k, batch, t)
        return preds.mean(dim=0), preds.std(dim=0)
