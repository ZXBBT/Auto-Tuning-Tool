# Project Dynamis

> Working codename — rename freely. *Dynamis* (δύναμις, "power / potential").

An automated, **physics-informed** engineering pipeline that analyzes vehicle ECU
data logs and calibration maps, learns the underlying engine physics, and proposes
**optimized calibration adjustments** to improve performance — bounded at every step
by hard safety limits and kept human-in-the-loop.

## Status

🟢 **v1 pipeline running on simulated data.** The full spine is built and tested —
physics → data → calibration → surrogate (+uncertainty) → constrained optimizer.
Training currently runs on **simulator-generated** data; calibrating against real
EA888 logs (the M3 anchor) is the remaining step to make outputs trustworthy.
Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The one-paragraph idea

Clean, paired `(map-change → outcome)` datasets barely exist online, so we don't try to
learn tuning end-to-end from scraped logs. Instead we build a **differentiable, mean-value
engine model** (physics for structure), **anchor it to abundant real wide-open-throttle
logs** (data for the residuals), and then **optimize *through* that model** under safety
constraints to find calibration changes that increase performance. The first version
targets **steady-state peak power** on **VAG EA888 (MK7 GTI/Golf R)**.

## Scope at a glance (v1)

| Dimension      | v1 choice                                                            |
|----------------|---------------------------------------------------------------------|
| Data           | Simulator-first; real WOT logs as calibration/validation anchor     |
| Simulator      | Differentiable Python mean-value engine model (gray-box)            |
| Model          | Physics-informed forward model, **inverted via constrained optimization** |
| Objective      | Steady-state **peak power** (WOT)                                    |
| Platforms      | **VAG EA888 (MK7 GTI/Golf R)** — v1 target; N55 secondary           |
| Output         | **Advisory** map-change recommendations + confidence (no auto-flash) |

## Development

Python 3.10+, isolated venv. PyTorch uses the **CUDA 12.8** wheel (Blackwell / RTX 50-series; CPU-only also fine).

```bash
python3 -m venv .venv --without-pip                       # system python may lack ensurepip
curl -fsSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu128   # omit for CPU-only
.venv/bin/pip install -e ".[ml,dev]"
.venv/bin/python -m pytest -q
```

## Usage

All commands assume the venv above (the project is installed editable there, so no
`PYTHONPATH` is needed). Stages that don't need PyTorch (`make_synthetic_log`,
`calibrate_demo`, `add_log_to_corpus`) also run with `PYTHONPATH=src python3 <script>`.

> Training currently uses **simulator-generated** data (simulator-first). It validates the
> machinery and is *not* a substitute for real-data calibration — see Status.

```bash
# 1. Generate a synthetic COBB-style WOT log, then ingest + QA it
.venv/bin/python scripts/make_synthetic_log.py

# 2. Calibrate the physics model (M3): fit theta_phys; parameter-recovery on sim data
.venv/bin/python scripts/calibrate_demo.py

# 3. Train the surrogate model (M4): NN deep-ensemble + uncertainty (uses the GPU if present)
.venv/bin/python scripts/train_surrogate.py

# 4. Optimize a tune (M6): maximize power within the safety limits
.venv/bin/python scripts/optimize_demo.py

# 5. Add a real log to the curated corpus (fill the metadata template first)
cp configs/metadata_template.yaml mylog.yaml          # then edit: fuel / mods / source
.venv/bin/python scripts/add_log_to_corpus.py mylog.csv mylog.yaml

# Run the test suite
.venv/bin/python -m pytest -q
```

`train_surrogate.py` reports held-out accuracy and how uncertainty grows out-of-domain;
`optimize_demo.py` prints the recommended spark/boost/λ across the RPM sweep, the active
safety limit at each point, and the predicted gain over a baseline.

## Intended use & boundaries

Off-road / track / dyno / research use. Recommendations are advisory and require
human + dyno validation before anything is flashed. No emissions-control-defeat
functionality. See [Safety, Legal & Ethics](docs/ARCHITECTURE.md#12-safety-legal--ethics).
