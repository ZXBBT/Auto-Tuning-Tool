"""Neural surrogate: a small MLP emulating the MVEM (perf = f(inputs))."""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch import nn

from .data import FEATURES, TARGETS, Standardizer


class MLP(nn.Module):
    def __init__(self, n_in: int, n_out: int, hidden=(64, 64)):
        super().__init__()
        layers: list[nn.Module] = []
        d = n_in
        for h in hidden:
            layers += [nn.Linear(d, h), nn.SiLU()]
            d = h
        layers.append(nn.Linear(d, n_out))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def best_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


class Surrogate:
    """One MLP surrogate with input/target standardization."""

    def __init__(self, features=FEATURES, targets=TARGETS, hidden=(64, 64), device: str | None = None):
        self.features = list(features)
        self.targets = list(targets)
        self.hidden = hidden
        self.device = device or best_device()
        self.xs = Standardizer()
        self.ys = Standardizer()
        self.model: MLP | None = None

    def fit(self, df: pd.DataFrame, epochs: int = 500, lr: float = 1e-3, seed: int = 0) -> "Surrogate":
        torch.manual_seed(seed)
        x = self.xs.fit_transform(df[self.features].to_numpy(dtype=float))
        y = self.ys.fit_transform(df[self.targets].to_numpy(dtype=float))
        xt = torch.tensor(x, dtype=torch.float32, device=self.device)
        yt = torch.tensor(y, dtype=torch.float32, device=self.device)

        self.model = MLP(len(self.features), len(self.targets), self.hidden).to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()
        self.model.train()
        for _ in range(epochs):
            opt.zero_grad()
            loss = loss_fn(self.model(xt), yt)
            loss.backward()
            opt.step()
        return self

    @torch.no_grad()
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict targets in original units; shape (n_rows, n_targets)."""
        assert self.model is not None, "call fit() first"
        self.model.eval()
        x = self.xs.transform(df[self.features].to_numpy(dtype=float))
        xt = torch.tensor(x, dtype=torch.float32, device=self.device)
        y = self.model(xt).cpu().numpy()
        return self.ys.inverse(y)
