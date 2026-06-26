"""Tests for the M6 constrained optimizer. Skipped if torch isn't installed."""

from __future__ import annotations

import pytest

pytest.importorskip("torch")

from dynamis.model.data import make_dataset  # noqa: E402
from dynamis.model.ensemble import DeepEnsemble  # noqa: E402
from dynamis.optimize import SafetyLimits, optimize_sweep  # noqa: E402


@pytest.fixture(scope="module")
def ensemble():
    return DeepEnsemble(k=3, hidden=(48, 48)).fit(make_dataset(n=600, seed=0), epochs=400)


def test_respects_box_constraints(ensemble):
    lim = SafetyLimits(boost_max_bar=1.8)
    res = optimize_sweep(ensemble, [3000, 4500, 6000], limits=lim, steps=300)
    t = res.table
    assert (t["boost_bar"] <= lim.boost_max_bar + 1e-2).all()
    assert (t["boost_bar"] >= lim.boost_min_bar - 1e-2).all()
    assert (t["lambda"] >= lim.lam_min - 1e-2).all()
    assert (t["lambda"] <= lim.lam_max + 1e-2).all()
    assert (t["spark_deg"] >= lim.spark_min - 0.1).all()
    assert (t["spark_deg"] <= lim.spark_max + 0.1).all()


def test_knock_margin_constraint_satisfied(ensemble):
    lim = SafetyLimits(knock_margin_min=0.10, sigma_k=0.0)
    res = optimize_sweep(ensemble, [4000, 5500, 6500], limits=lim, steps=500)
    # soft constraint -> allow a small tolerance
    assert res.table["knock_margin"].min() >= lim.knock_margin_min - 0.03


def test_optimizer_beats_baseline(ensemble):
    res = optimize_sweep(ensemble, list(range(3000, 6801, 600)), steps=500)
    assert res.gain_hp > 0.0  # optimized peak power exceeds the conservative baseline
