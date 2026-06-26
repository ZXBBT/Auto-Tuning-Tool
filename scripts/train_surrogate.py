"""Train the M4 surrogate ensemble on sim data; report accuracy + uncertainty.

Run (in the venv):  .venv/bin/python scripts/train_surrogate.py

This is sim-data training: it validates the surrogate machinery (held-out accuracy) and
the uncertainty behaviour (sigma grows out-of-domain). It is NOT validation vs reality.
"""

from __future__ import annotations

import numpy as np

from dynamis.model.data import BOOST_BAR, TARGETS, make_dataset, sample_inputs, simulate_targets
from dynamis.model.ensemble import DeepEnsemble
from dynamis.model.surrogate import best_device


def _metrics(true: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    mae = float(np.mean(np.abs(true - pred)))
    ss_res = float(np.sum((true - pred) ** 2))
    ss_tot = float(np.sum((true - true.mean()) ** 2)) or 1.0
    return mae, 1.0 - ss_res / ss_tot


def main() -> int:
    print(f"device: {best_device()}")
    train = make_dataset(n=2500, seed=0)
    test = make_dataset(n=600, seed=1)

    ens = DeepEnsemble(k=5).fit(train, epochs=800)
    mean, std = ens.predict(test)

    print("\n=== held-out accuracy (in-domain) ===")
    print(f"{'target':>14} {'MAE':>10} {'R2':>8} {'mean_sigma':>12}")
    print("-" * 46)
    for i, t in enumerate(TARGETS):
        mae, r2 = _metrics(test[t].to_numpy(), mean[:, i])
        print(f"{t:>14} {mae:>10.3f} {r2:>8.4f} {std[:, i].mean():>12.4f}")

    # uncertainty should grow OUT of the training domain (extrapolated boost)
    in_dom = sample_inputs(300, seed=7, boost_bar=BOOST_BAR)
    ood = sample_inputs(300, seed=7, boost_bar=(2.4, 3.2))  # beyond training (0.3-2.0 bar)
    _, std_in = ens.predict(simulate_targets(in_dom))
    _, std_ood = ens.predict(simulate_targets(ood))

    print("\n=== uncertainty: in-domain vs out-of-domain (extrapolated boost) ===")
    for i, t in enumerate(TARGETS):
        print(f"  {t:>14}: sigma_in={std_in[:, i].mean():.4f}  sigma_ood={std_ood[:, i].mean():.4f}")
    grew = all(std_ood[:, i].mean() > std_in[:, i].mean() for i in range(len(TARGETS)))
    print(f"\nuncertainty grows out-of-domain: {'YES' if grew else 'NO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
