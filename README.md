# Project Dynamis

> Working codename — rename freely. *Dynamis* (δύναμις, "power / potential").

An automated, **physics-informed** engineering pipeline that analyzes vehicle ECU
data logs and calibration maps, learns the underlying engine physics, and proposes
**optimized calibration adjustments** to improve performance — bounded at every step
by hard safety limits and kept human-in-the-loop.

## Status

🚧 **Pre-implementation.** This repository currently contains the **architecture and
design only** — no code yet. Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The one-paragraph idea

Clean, paired `(map-change → outcome)` datasets barely exist online, so we don't try to
learn tuning end-to-end from scraped logs. Instead we build a **differentiable, mean-value
engine model** (physics for structure), **anchor it to abundant real wide-open-throttle
logs** (data for the residuals), and then **optimize *through* that model** under safety
constraints to find calibration changes that increase performance. The first version
targets **steady-state peak power** on **BMW N55 / VAG EA888**.

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

## Intended use & boundaries

Off-road / track / dyno / research use. Recommendations are advisory and require
human + dyno validation before anything is flashed. No emissions-control-defeat
functionality. See [Safety, Legal & Ethics](docs/ARCHITECTURE.md#12-safety-legal--ethics).
