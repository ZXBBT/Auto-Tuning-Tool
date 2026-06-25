"""Physics-trend tests for the v0 MVEM. Run: PYTHONPATH=src pytest -q"""

from __future__ import annotations

from dynamis.config import EA888_GEN3
from dynamis.physics import OperatingPoint, simulate_wot

P_ATM = 101325.0


def _op(boost_bar=1.2, rpm=5500, temp=320.0, lam=0.85, octane=98.0):
    return OperatingPoint(rpm, P_ATM + boost_bar * 1e5, temp, lam=lam, octane=octane)


def test_power_increases_with_boost():
    lo = simulate_wot(_op(boost_bar=0.6), EA888_GEN3)
    hi = simulate_wot(_op(boost_bar=1.6), EA888_GEN3)
    assert hi.power_hp > lo.power_hp


def test_knock_limit_falls_with_boost():
    lo = simulate_wot(_op(boost_bar=0.6), EA888_GEN3)
    hi = simulate_wot(_op(boost_bar=1.8), EA888_GEN3)
    assert hi.knock_limited_deg <= lo.knock_limited_deg


def test_octane_allows_more_timing():
    low = simulate_wot(_op(boost_bar=1.6, octane=91), EA888_GEN3)
    high = simulate_wot(_op(boost_bar=1.6, octane=104), EA888_GEN3)
    assert high.knock_limited_deg >= low.knock_limited_deg


def test_hot_charge_pulls_timing():
    cool = simulate_wot(_op(boost_bar=1.6, temp=300), EA888_GEN3)
    hot = simulate_wot(_op(boost_bar=1.6, temp=380), EA888_GEN3)
    assert hot.knock_limited_deg <= cool.knock_limited_deg


def test_richer_improves_knock_margin_fixed_spark():
    eng = EA888_GEN3
    lean = simulate_wot(_op(boost_bar=1.8, lam=0.98), eng, spark_deg=12.0)
    rich = simulate_wot(_op(boost_bar=1.8, lam=0.78), eng, spark_deg=12.0)
    assert rich.knock_margin >= lean.knock_margin


def test_peak_power_in_sane_range():
    peak = max(
        simulate_wot(_op(boost_bar=b, rpm=6000), EA888_GEN3).power_hp
        for b in (0.4, 0.8, 1.2, 1.6, 2.0)
    )
    assert 200.0 <= peak <= 460.0


def test_low_boost_is_mbt_limited_not_knock_limited():
    r = simulate_wot(_op(boost_bar=0.3, octane=98), EA888_GEN3)
    assert not r.knock_limited
    assert r.knock_margin > 0.0
