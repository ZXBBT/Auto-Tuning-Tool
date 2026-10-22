"""Simulated live ECU data: a looping drive cycle encoded as CAN frames.

The cycle (idle -> 3rd-gear WOT pull -> lift-off -> cruise) is precomputed once. The
WOT segment comes from the MVEM (knock-limited spark, torque); the part-throttle
segments are simple heuristics, since the MVEM only models WOT. Knock events are
injected where the model says the engine is running close to the knock limit.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from ..config import EA888_GEN3
from ..config.engine import EngineParams
from ..physics import OperatingPoint, simulate_wot
from ..physics.constants import P_ATM
from .can import EA888_FRAMES, encode

TICK_S = 0.05  # 20 Hz, matches the frames' period_ms


@dataclass
class CanFrame:
    t: float
    frame_id: int
    data: bytes


def _segment(n: int, **cols) -> dict[str, np.ndarray]:
    return {k: np.broadcast_to(np.asarray(v, dtype=float), (n,)).copy() for k, v in cols.items()}


def build_cycle(engine: EngineParams = EA888_GEN3, octane: float = 98.0, seed: int = 0) -> dict[str, np.ndarray]:
    """One pass of the drive cycle as channel arrays sampled every TICK_S."""
    rng = np.random.default_rng(seed)
    segs: list[dict[str, np.ndarray]] = []

    n = int(4.0 / TICK_S)  # idle
    segs.append(_segment(n, rpm=800 + rng.normal(0, 15, n), torque_nm=25, pedal_pct=0, gear=0,
                         map_kpa=35, charge_temp_c=34, **{"lambda": 1.0}, ignition_deg=8))

    n = int(8.0 / TICK_S)  # WOT pull, 3rd gear, 2500 -> 6800 rpm
    cols: dict[str, list[float]] = {k: [] for k in ("rpm", "torque_nm", "map_kpa", "charge_temp_c", "ignition_deg")}
    margin = []
    for i in range(n):
        frac = i / (n - 1)
        rpm = 2500.0 + frac * 4300.0
        boost_bar = min(1.45, 1.45 * (1.0 - np.exp(-(rpm - 2000.0) / 700.0)))
        charge_c = 36.0 + 14.0 * frac
        r = simulate_wot(OperatingPoint(rpm, P_ATM + boost_bar * 1e5, charge_c + 273.15, 0.85, octane), engine)
        cols["rpm"].append(rpm)
        cols["torque_nm"].append(r.torque_nm)
        cols["map_kpa"].append((P_ATM + boost_bar * 1e5) / 1000.0)
        cols["charge_temp_c"].append(charge_c)
        cols["ignition_deg"].append(r.spark_deg)
        margin.append(r.knock_margin)
    wot = {k: np.asarray(v) for k, v in cols.items()}
    wot.update(_segment(n, pedal_pct=100, gear=3, **{"lambda": 0.85 + rng.normal(0, 0.004, n)}))
    segs.append(wot)
    near_limit = np.asarray(margin) < 0.15

    n = int(2.0 / TICK_S)  # lift-off: fuel cut, rpm falls
    segs.append(_segment(n, rpm=np.linspace(6800, 3200, n), torque_nm=-30, pedal_pct=0, gear=3,
                         map_kpa=np.linspace(240, 30, n), charge_temp_c=50, **{"lambda": 1.0},
                         ignition_deg=5))

    n = int(6.0 / TICK_S)  # light cruise
    segs.append(_segment(n, rpm=2100 + rng.normal(0, 10, n), torque_nm=70, pedal_pct=18, gear=5,
                         map_kpa=55, charge_temp_c=np.linspace(50, 40, n),
                         **{"lambda": 1.0 + rng.normal(0, 0.003, n)}, ignition_deg=28))

    cyc = {k: np.concatenate([s[k] for s in segs]) for k in segs[0]}
    total = len(cyc["rpm"])
    i0 = len(segs[0]["rpm"])
    for c in range(1, 5):  # sporadic per-cylinder knock retard near the knock limit only
        kr = np.zeros(total)
        hits = near_limit & (rng.random(len(near_limit)) < 0.15)
        kr[i0:i0 + len(near_limit)][hits] = np.clip(rng.normal(1.5, 0.8, hits.sum()), 0.3, 4.0)
        cyc[f"knock_retard_cyl{c}"] = kr
    # the ECU pulls timing on knock: logged ignition = base spark - worst-cylinder retard
    cyc["ignition_deg"] -= np.max([cyc[f"knock_retard_cyl{c}"] for c in range(1, 5)], axis=0)
    return cyc


def frames(cycle: dict[str, np.ndarray]) -> Iterator[list[CanFrame]]:
    """Endless iterator: one list of CAN frames (one per frame definition) per tick."""
    n = len(cycle["rpm"])
    tick = 0
    while True:
        i = tick % n
        values = {k: float(v[i]) for k, v in cycle.items()}
        t = round(tick * TICK_S, 3)
        yield [CanFrame(t, f.frame_id, encode(f, values, counter=tick)) for f in EA888_FRAMES]
        tick += 1
