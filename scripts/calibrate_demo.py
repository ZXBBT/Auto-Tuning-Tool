"""Parameter-recovery demo: train theta_phys on sim data, recover injected params.

Run:  PYTHONPATH=src python3 scripts/calibrate_demo.py

For each block: pick TRUE params, generate a labeled sim dataset, then fit starting from
the stock priors and check the fit recovers the TRUE values. This validates the M3
calibration machinery (and shows which parameters are identifiable from WOT data).
"""

from __future__ import annotations

from dataclasses import replace

from dynamis.calibration.dataset import label_dataset, make_grid
from dynamis.calibration.fit import calibrate
from dynamis.config import EA888_GEN3


def recover(title, free, true_overrides, targets, bounds, spark=15.0):
    true_eng = replace(EA888_GEN3, **true_overrides)
    df = label_dataset(make_grid(spark_deg=spark), true_eng, targets)

    init = [getattr(EA888_GEN3, p) for p in free]
    res = calibrate(df, EA888_GEN3, free, targets, init, bounds)

    print(f"\n=== {title} ===  (targets: {', '.join(targets)})")
    print(f"{'param':>20} {'init':>12} {'true':>12} {'fitted':>12} {'err%':>7}")
    print("-" * 67)
    ok = True
    for p, x0 in zip(free, init):
        true = true_overrides[p]
        fit = res.fitted[p]
        err = abs(fit - true) / (abs(true) or 1.0) * 100
        ok = ok and err < 5.0
        print(f"{p:>20} {x0:>12.4g} {true:>12.4g} {fit:>12.4g} {err:>6.1f}%")
    rmse = ", ".join(f"{k}={v:.3g}" for k, v in res.rmse.items())
    print(f"  residual RMSE: {rmse}   success={res.success}")
    return ok


def main() -> int:
    results = []
    results.append(
        recover(
            "Volumetric efficiency (from air mass per stroke)",
            ["ve_peak", "ve_rpm_peak"],
            {"ve_peak": 0.96, "ve_rpm_peak": 4800.0},
            ["air_mass_per_stroke_mg"],
            [(0.6, 1.1), (2000.0, 7000.0)],
        )
    )
    results.append(
        recover(
            "Thermal efficiency + friction (from torque)",
            ["eta_thermal_base", "fmep_pa"],
            {"eta_thermal_base": 0.39, "fmep_pa": 1.7e5},
            ["torque_nm"],
            [(0.25, 0.45), (0.5e5, 3.0e5)],
        )
    )
    results.append(
        recover(
            "Knock constant (from knock-limited spark)",
            ["knock_A"],
            {"knock_A": 21.0},
            ["knock_limited_deg"],
            [(5.0, 40.0)],
            spark=15.0,
        )
    )

    print("\n=== parameter-recovery summary ===")
    for name, ok in zip(["VE", "efficiency", "knock"], results):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} recovered within 5%")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
