"""Qualitative sanity check for the v0 MVEM (M2 deliverable).

Run:  PYTHONPATH=src python3 scripts/sanity_mvem.py

Prints an RPM power sweep plus three "ignition timing pull" demonstrations (boost,
octane, IAT), and asserts the physically-expected trends so the file doubles as a test
even when pytest is unavailable.
"""

from __future__ import annotations

from dynamis.config import EA888_GEN3
from dynamis.physics import OperatingPoint, simulate_wot

P_ATM = 101325.0


def boost_to_pim(boost_bar: float) -> float:
    return P_ATM + boost_bar * 1e5


def rpm_sweep() -> None:
    eng = EA888_GEN3
    print(f"\n=== RPM sweep @ WOT — {eng.name} ===")
    print("  (boost 1.2 bar, charge 320 K, lambda 0.85, 98 RON)\n")
    hdr = f"{'rpm':>5} {'VE':>5} {'air':>6} {'MBT':>5} {'kLim':>5} {'spk':>5} {'kMrg':>5} {'Nm':>6} {'hp':>6} {'EGT':>5}"
    print(hdr)
    print("-" * len(hdr))
    for rpm in range(2500, 7001, 500):
        op = OperatingPoint(rpm=rpm, p_im_pa=boost_to_pim(1.2), charge_temp_k=320.0)
        r = simulate_wot(op, eng)
        print(
            f"{rpm:>5} {r.eta_vol:>5.2f} {r.m_dot_air:>6.3f} {r.mbt_deg:>5.1f} "
            f"{r.knock_limited_deg:>5.1f} {r.spark_deg:>5.1f} {r.knock_margin:>5.2f} "
            f"{r.torque_nm:>6.0f} {r.power_hp:>6.0f} {r.egt_c:>5.0f}"
        )


def sweep(title: str, values, make_op, label: str, spark_deg=None):
    eng = EA888_GEN3
    print(f"\n=== {title} ===")
    print(f"{label:>8} {'kLim':>6} {'spk':>6} {'kMrg':>6} {'hp':>6}")
    print("-" * 34)
    rows = []
    for v in values:
        r = simulate_wot(make_op(v), eng, spark_deg=spark_deg)
        rows.append((v, r))
        print(f"{v:>8.2f} {r.knock_limited_deg:>6.1f} {r.spark_deg:>6.1f} {r.knock_margin:>6.2f} {r.power_hp:>6.0f}")
    return rows


def main() -> int:
    rpm_sweep()

    boost_rows = sweep(
        "Timing pull vs BOOST (5500 rpm, 320 K, 98 RON)",
        [0.4, 0.8, 1.2, 1.6, 2.0],
        lambda b: OperatingPoint(5500, boost_to_pim(b), 320.0),
        "boost",
    )
    oct_rows = sweep(
        "Timing recovery vs OCTANE (5500 rpm, 1.6 bar, 320 K)",
        [91, 95, 98, 101, 104],
        lambda o: OperatingPoint(5500, boost_to_pim(1.6), 320.0, octane=float(o)),
        "RON",
    )
    iat_rows = sweep(
        "Timing pull vs CHARGE TEMP (5500 rpm, 1.6 bar, 98 RON)",
        [300, 320, 340, 360, 380],
        lambda t: OperatingPoint(5500, boost_to_pim(1.6), float(t)),
        "T[K]",
    )
    lam_rows = sweep(
        "Knock margin vs LAMBDA (5500 rpm, 1.8 bar, 320 K, fixed 12 deg)",
        [0.75, 0.82, 0.90, 0.98],
        lambda lm: OperatingPoint(5500, boost_to_pim(1.8), 320.0, lam=lm),
        "lambda",
        spark_deg=12.0,
    )

    # --- physical-trend assertions ---
    checks = []
    klim_vs_boost = [r.knock_limited_deg for _, r in boost_rows]
    checks.append(("knock limit falls as boost rises",
                   all(x >= y - 1e-6 for x, y in zip(klim_vs_boost, klim_vs_boost[1:]))))
    klim_vs_oct = [r.knock_limited_deg for _, r in oct_rows]
    checks.append(("knock limit rises with octane",
                   all(x <= y + 1e-6 for x, y in zip(klim_vs_oct, klim_vs_oct[1:]))))
    klim_vs_iat = [r.knock_limited_deg for _, r in iat_rows]
    checks.append(("knock limit falls as charge temp rises",
                   all(x >= y - 1e-6 for x, y in zip(klim_vs_iat, klim_vs_iat[1:]))))
    # lam_rows go rich -> lean, so knock margin (at fixed spark) should be non-increasing
    kmrg_vs_lam = [r.knock_margin for _, r in lam_rows]
    checks.append(("richer mixture improves knock margin",
                   all(x >= y - 1e-6 for x, y in zip(kmrg_vs_lam, kmrg_vs_lam[1:]))))
    hp_vs_boost = [r.power_hp for _, r in boost_rows]
    checks.append(("power rises with boost",
                   all(x <= y + 1e-6 for x, y in zip(hp_vs_boost, hp_vs_boost[1:]))))
    # peak power in a sane range for a tuned EA888
    peak_hp = max(r.power_hp for _, r in boost_rows)
    checks.append(("peak power in sane range (200-450 hp)", 200.0 <= peak_hp <= 450.0))

    print("\n=== physical-trend checks ===")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
