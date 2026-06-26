"""Deep ensemble of surrogates -> predictive mean + uncertainty (sigma)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from .data import FEATURES, TARGETS
from .surrogate import MLP, Surrogate


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

    def save(self, path: str) -> None:
        blob = {
            "k": self.k,
            "features": self.features,
            "targets": self.targets,
            "hidden": self.hidden,
            "members": [
                {"state": m.model.state_dict(), "xs": (m.xs.mean, m.xs.std), "ys": (m.ys.mean, m.ys.std)}
                for m in self.members
            ],
        }
        torch.save(blob, path)

    @classmethod
    def load(cls, path: str, device: str | None = None) -> "DeepEnsemble":
        blob = torch.load(path, map_location=device or "cpu", weights_only=False)
        ens = cls(k=blob["k"], features=blob["features"], targets=blob["targets"], hidden=blob["hidden"], device=device)
        members = []
        for md in blob["members"]:
            s = Surrogate(blob["features"], blob["targets"], tuple(blob["hidden"]), device)
            s.model = MLP(len(blob["features"]), len(blob["targets"]), tuple(blob["hidden"])).to(s.device)
            s.model.load_state_dict(md["state"])
            s.model.eval()
            s.xs.mean, s.xs.std = md["xs"]
            s.ys.mean, s.ys.std = md["ys"]
            members.append(s)
        ens.members = members
        return ens
