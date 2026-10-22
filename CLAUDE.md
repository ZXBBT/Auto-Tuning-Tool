# CLAUDE.md — Project Dynamis

Persistent context for Claude Code. Loaded automatically at the start of every session
started in this directory. Keep it current when decisions, status, or conventions change.
The authoritative deep spec is **`docs/ARCHITECTURE.md`** (v0.2) — this file is the
fast-load summary and points there.

---

## What this project is

An **automated, AI-assisted, physics-informed ECU calibration pipeline** for
high-performance vehicles. Core intent (user's words): *"train a model that understands
the laws of physics in the engine and knows which parameters in the ECU map to change in
order to achieve higher performance."*

The system (a) analyzes ECU data logs and binary maps, (b) evaluates performance
bottlenecks (ignition timing pull, boost deviations, fueling inefficiencies), and
(c) intelligently generates optimized calibration adjustments.

- **Long-term goal:** custom tuning — user states a goal, system adjusts ECU params.
- **v1 goal (fixed):** steady-state **peak power** at WOT.
- **Primary platform:** VAG **EA888 Gen3** 2.0T (MK7 GTI / Golf R), COBB Accessport CSV
  logs. BMW N55 is the secondary platform.

## The approach (how it reasons)

Gray-box, **physics-informed, simulator-first**:

1. A 0-D **Mean-Value Engine Model (MVEM)** provides physical structure: speed-density
   volumetric efficiency, compressible-orifice throttle flow, turbo model, Wiebe
   combustion, single-zone closed-cycle in-cylinder pressure.
2. **Knock** = Livengood–Wu autoignition integral + Douaud–Eyzat ignition delay. This is
   the physical heart of "ignition timing pull."
3. **Air-limited heat release:** combustion heat ∝ *burnable* (stoichiometric-limited)
   fuel, not total fuel; excess fuel only cools the charge (why richer = less knock).
4. A **neural surrogate** (MLP) emulates the MVEM and is made **differentiable**
   (`forward_tensor`) so the optimizer can backprop to the decision variables.
5. A **deep ensemble** (K independently-trained surrogates) gives predictive mean + σ;
   optimization is σ-aware (conservative where the model is unsure).
6. A **constrained optimizer** maximizes torque subject to a σ-aware knock-margin floor
   and box limits (boost / λ / spark), batched over an RPM sweep.
7. **Diagnostics** separate observed findings (from log channels) from `(model)`-estimated
   findings (via the MVEM).

## ⚠️ Standing caveat (do not drop this)

All current numbers come from the **uncalibrated simulator**. The machinery is validated;
the tune is **not yet trustworthy**. Real-log calibration (**M3 proper**) is the gating
item for trustworthy output. Always state this when reporting optimizer/diagnostic
numbers. More *sim* data does not improve real-world fidelity (confirmed: the surrogate's
held-out error plateaus by ~2000 samples; the default n=3000 is already past it).

---

## Repo layout

- `docs/ARCHITECTURE.md` — source of truth (17 sections; decisions D1–D9; roadmap M0–M8;
  governing equations §7; unified log schema §8.1; optimization formulation §10;
  safety/legal §12).
- `docs/data-feasibility.md`, `docs/dataset-assessment.md` — data-sourcing scans.
- `src/dynamis/config/engine.py` — `EngineParams` frozen dataclass + `EA888_GEN3` (bore
  82.5mm, stroke 92.8mm, CR 9.6, 4-cyl) and calibratable θ_phys defaults (VE, knock A/a/n/B,
  thermal/combustion efficiency, …).
- `src/dynamis/physics/` — `volumetric`, `airpath` (speed-density), `fueling`,
  `combustion`, `knock` (Livengood–Wu), `mvem` (`simulate_wot`), `constants`.
- `src/dynamis/data/` — `schema` (CANONICAL_CHANNELS), `units`, `mapping` (`COBB_EA888`
  column aliases/units), `ingest`, `qa` (WOT detection), `synthetic`, `corpus` (curated,
  provenance-tracked log store).
- `src/dynamis/calibration/` — `predict` (cheap target predictors), `fit` (scipy
  least_squares, `diff_step=1e-3`), `dataset`.
- `src/dynamis/model/` — `data` (torch-free dataset gen), `surrogate` (MLP), `ensemble`
  (DeepEnsemble, save/load).
- `src/dynamis/optimize/` — `constraints` (`SafetyLimits`), `optimizer` (`optimize_sweep`).
- `src/dynamis/diagnostics/` — `detectors`, `report`.
- `src/dynamis/cli/` — `main` (typer app), `progress` (the `Pulse` progress reporter).
- `src/dynamis/api/` — FastAPI app (`app.create_app`), `service` (library → JSON glue),
  `jobs` (single-worker background jobs + SSE progress), `ratelimit` (per-IP token bucket).
- `src/dynamis/telemetry/` — `can` (DBC-style codec, CRC-8 J1850, alive counter; layout is
  illustrative), `stream` (looping simulated drive cycle → CAN frames for the WebSocket).
- `frontend/` — React + TS + Vite + Recharts web app (5 tabs). `deploy/` — Dockerfiles,
  Caddyfile, `DEPLOY.md`. Root: `compose.yaml` (+ `compose.direct.yaml` overlay), `.env.example`.
- `scripts/` — demo runners per stage. `tests/` — 10 files, 46 tests.

## Environment & commands

- Python **3.10.12**; venv at `/mnt/d/project/.venv` (created `--without-pip` + get-pip
  bootstrap because system Python lacked ensurepip — do **not** `apt`/sudo).
- Base deps: numpy/scipy/pandas/matplotlib/pyyaml/typer. ML extra: **PyTorch
  2.11.0+cu128** (CUDA 12.8) on **RTX 5070 Ti** (Blackwell, sm_120). Installed editable;
  CLI entry point `dynamis`.
- Always invoke the venv explicitly (the shell resets cwd between commands):
  ```bash
  cd /mnt/d/project && .venv/bin/python -m pytest -q      # 46 tests
  cd /mnt/d/project && .venv/bin/ruff check                # lint
  cd /mnt/d/project && .venv/bin/dynamis --help            # CLI
  cd /mnt/d/project && .venv/bin/uvicorn dynamis.api.app:create_app --factory --port 8000
  cd /mnt/d/project/frontend && . ~/.nvm/nvm.sh && npm run dev   # Vite proxies /api -> :8000
  cd /mnt/d/project && DOCKER_CONFIG=<empty dir> docker compose up -d --build  # -> :8080
  ```
- Node 22 via nvm in `~/.nvm` (user-space). Docker Desktop with WSL integration; its
  `credsStore: desktop.exe` helper fails from WSL, so run docker with `DOCKER_CONFIG`
  pointing at a dir holding `{}` (public images need no creds).
- CLI commands: `ingest`, `diagnose`, `make-synthetic`, `add-log`, `train`, `optimize`.
  `train`/`optimize` import torch lazily; the others work without it. Long jobs
  (data-gen, training, optimize) show a live `Pulse` progress bar.

## Conventions / lessons (things that bit us — keep them)

- **gitignore has no trailing comments** — put comments on their own line (a synthetic CSV
  once got committed because of `path/ # comment`).
- **Knock calibration finite-diff:** `diff_step=1e-3` (knock-limited spark is quantized by
  a binary search; a smaller step gives zero gradient).
- **Optimizer penalty is linear + quadratic** (`8*p + 80*p²`): a pure quadratic penalty's
  gradient vanishes at the boundary and under-enforces the knock-margin floor.
- **Ensemble σ uses population std** (`unbiased=False`) to match numpy `predict()` and
  avoid `nan` at k=1 — the optimizer consumes this σ.
- **Air-limited heat release:** use `min(m_dot_fuel, m_dot_air/afr_stoich)` for combustion
  heat; total fuel only for charge cooling.
- Scratch/analysis scripts go in the session scratchpad, **not** the repo.
- **torch `set_num_threads` is per-thread**: set it in the job worker (ThreadPoolExecutor
  initializer) or the optimizer runs ~10x slower there. First torch op from the venv on
  `/mnt/d` costs ~20 s (lazy lib loading over 9P); in Docker it's fast. API warms up at startup.
- **Recharts finds axes/grid/tooltip by element type** — wrapper *components* silently don't
  render; `frontend/src/components/axes.tsx` exposes plain functions returning elements.

## Status & roadmap

Done: **M0** (architecture) → **M0.5** (data feasibility) → **M1** (physics MVEM) →
**M2** (knock + air-limited fix) → **M4** (surrogate + deep ensemble) →
**M5** (diagnostics) → **M6** (constrained optimizer) → **M7** (CLI). Plus: senior code
audit (clean), and a live progress `Pulse` for long jobs.

**Web demo (Oct 2026, for the user's embedded-software-developer job interview — role covers
network/frontend/backend/DNS):** W1 backend API ✅, W2 frontend ✅, W3 Docker+Caddy ✅ (verified
locally on :8080). W4 public exposure pending the user's domain: path **A** Cloudflare Tunnel
(primary, for the live demo) + path **B** direct (router port-forward, DDNS, Let's Encrypt) on a
second subdomain — user confirmed no CGNAT. W5: README/resume bullets/demo script.

**Pending:**
- **M3 proper (real-data calibration)** — the gating item. User is sourcing a real EA888
  COBB WOT log ("I'll let you know once I found the new data"). When provided: refine
  `COBB_EA888` aliases/units to the real file's header, then run
  `dynamis add-log <csv> <metadata.yaml>` and calibrate.
- **M8 (binary-map read)** — parse a real EA888 `.bin` (Simos18) into the table model. Last
  remaining code milestone; not started.

## Working style with this user

- The user directs milestones **one at a time** — confirm before starting the next; don't
  autonomously jump ahead.
- Declined a mass web scraper for logs (metadata like fuel/mods/turbo isn't in the files →
  low value; plus ToS/consent). Agreed path: curated manual collection + licensed datasets.
- Be honest about what's validated vs. simulated; report failures plainly.
- GitHub remote: `github.com/ZXBBT/Auto-Tuning-Tool` (private, SSH). Commit/push only when
  asked.
