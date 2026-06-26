"""M6 demo: train the surrogate on sim data, then optimize the WOT calibration.

Run (in the venv):  .venv/bin/python scripts/optimize_demo.py

Produces a recommended spark/boost/lambda map across the RPM sweep that maximizes power
within the safety limits, plus the predicted gain over a conservative baseline. (Sim-data
machinery demo — trustworthy numbers require real-data calibration.)
"""

from __future__ import annotations

from dynamis.model.data import make_dataset
from dynamis.model.ensemble import DeepEnsemble
from dynamis.model.surrogate import best_device
from dynamis.optimize import SafetyLimits, optimize_sweep


def main() -> int:
    print(f"device: {best_device()}\ntraining surrogate ensemble on sim data...")
    ens = DeepEnsemble(k=5).fit(make_dataset(n=3000, seed=0), epochs=800)

    limits = SafetyLimits(knock_margin_min=0.10, boost_max_bar=1.8, sigma_k=1.0)
    rpms = list(range(3000, 6801, 400))
    res = optimize_sweep(ens, rpms, charge_temp_c=50.0, octane=98.0, limits=limits)

    print("\n=== recommended WOT calibration (98 RON, 50 degC charge) ===")
    print(res.table.to_string(index=False))
    print(
        f"\npeak power: {res.peak_power_hp:.0f} hp   "
        f"baseline: {res.baseline_peak_hp:.0f} hp   "
        f"gain: +{res.gain_hp:.0f} hp"
    )

    # check the safety constraint actually held
    worst = res.table["knock_margin"].min()
    print(f"min knock margin across sweep: {worst:.3f}  (limit {limits.knock_margin_min:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
