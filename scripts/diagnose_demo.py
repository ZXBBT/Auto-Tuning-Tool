"""M5 demo: diagnose a log for performance bottlenecks.

Run:  PYTHONPATH=src python3 scripts/diagnose_demo.py   (or via .venv/bin/python)

Generates a deliberately CONSERVATIVE synthetic tune (timing pulled 4 deg below the
model's limit) so the detectors have something to find, then prints the bottleneck report.
"""

from __future__ import annotations

from dynamis.data import COBB_EA888, generate_cobb_wot_log, ingest_dataframe
from dynamis.diagnostics import diagnose


def main() -> int:
    raw = generate_cobb_wot_log(seed=3, spark_offset_deg=-4.0)
    lf = ingest_dataframe(raw, COBB_EA888, meta={"vehicle": "synthetic EA888 (conservative tune)"})
    print(diagnose(lf, octane=98.0).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
