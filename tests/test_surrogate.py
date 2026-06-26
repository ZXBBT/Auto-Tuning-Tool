"""Tests for the M4 surrogate ensemble. Skipped if torch isn't installed."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("torch")

from dynamis.model.data import TARGETS, make_dataset, sample_inputs, simulate_targets  # noqa: E402
from dynamis.model.ensemble import DeepEnsemble  # noqa: E402


def test_surrogate_fits_held_out():
    train = make_dataset(n=400, seed=0)
    test = make_dataset(n=120, seed=1)
    ens = DeepEnsemble(k=3, hidden=(48, 48)).fit(train, epochs=400)
    mean, std = ens.predict(test)

    tq = TARGETS.index("torque_nm")
    mae = float(np.mean(np.abs(mean[:, tq] - test["torque_nm"].to_numpy())))
    assert mae < 18.0  # Nm, against torques of ~250-450
    assert (std >= 0).all() and std.mean() > 0.0


def test_uncertainty_grows_out_of_domain():
    train = make_dataset(n=400, seed=0)
    ens = DeepEnsemble(k=3, hidden=(48, 48)).fit(train, epochs=400)

    in_dom = simulate_targets(sample_inputs(150, seed=5))
    ood = simulate_targets(sample_inputs(150, seed=5, boost_bar=(2.6, 3.4)))
    _, std_in = ens.predict(in_dom)
    _, std_ood = ens.predict(ood)
    assert std_ood.mean() > std_in.mean()
