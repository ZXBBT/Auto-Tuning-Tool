"""Generate a synthetic COBB-style EA888 WOT log, then ingest + QA it end-to-end.

Run:  PYTHONPATH=src python3 scripts/make_synthetic_log.py
Writes data/synthetic/ea888_sample_wot.csv (gitignored) and prints the QA report.
"""

from __future__ import annotations

import json
from pathlib import Path

from dynamis.data import COBB_EA888, generate_cobb_wot_log, load_csv, qa_report

OUT = Path("data/synthetic/ea888_sample_wot.csv")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    raw = generate_cobb_wot_log(seed=1)
    raw.to_csv(OUT, index=False)
    print(f"wrote {OUT}  ({len(raw)} rows, {len(raw.columns)} source columns)")

    lf = load_csv(str(OUT), profile=COBB_EA888, meta={"fuel": "98 RON", "vehicle": "synthetic EA888"})
    print("\n=== canonical channels ===")
    print(", ".join(lf.channels))
    print("\n=== QA report ===")
    print(json.dumps(qa_report(lf), indent=2, default=str))

    print("\n=== canonical sample (WOT rows) ===")
    cols = ["time_s", "rpm", "map_kpa", "boost_kpa", "lambda", "ignition_deg", "knock_retard_deg", "charge_temp_c"]
    cols = [c for c in cols if c in lf.df.columns]
    print(lf.df[lf.df["pedal_pct"] >= 95][cols].iloc[::20].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
