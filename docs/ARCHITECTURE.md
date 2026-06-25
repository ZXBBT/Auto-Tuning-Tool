# Project Dynamis — Architecture

**Status:** Revised after goal-fit review · **Version:** 0.2 · **Scope:** v1 design

> This document is the single source of truth for *what we are building and why*,
> before any code is written. It is intentionally detailed so the design can be
> reviewed and corrected up front. Working codename **Dynamis**; rename freely.
>
> **v0.2 changelog:** diagnostics promoted to a first-class capability/module/milestone;
> real-time scope set to *offline-first, live-streaming as a later track*; added the
> knock-limit identification strategy (§7.4), a validation protocol (§9.5), a data
> feasibility gate (M0.5), an optimization baseline definition (§10.2), and a binary-read
> milestone (M8); re-rated knock and data-acquisition risks.

---

## Table of contents

1. [Vision](#1-vision)
2. [Goals & non-goals (v1)](#2-goals--non-goals-v1)
3. [Design principles](#3-design-principles)
4. [Decisions to date](#4-decisions-to-date)
5. [System architecture](#5-system-architecture)
6. [Component breakdown](#6-component-breakdown)
7. [The physics model](#7-the-physics-model)
8. [Data model & schemas](#8-data-model--schemas)
9. [The learning approach](#9-the-learning-approach)
10. [The optimization formulation](#10-the-optimization-formulation)
11. [Tech stack](#11-tech-stack)
12. [Safety, legal & ethics](#12-safety-legal--ethics)
13. [Repository layout](#13-repository-layout)
14. [Roadmap & milestones](#14-roadmap--milestones)
15. [Risks & mitigations](#15-risks--mitigations)
16. [Open questions](#16-open-questions)
17. [Glossary](#17-glossary)

---

## 1. Vision

Build a system that has **internalized engine physics** well enough to reason:
*"to gain performance here, move these calibration cells, and here is the physical
limit that stops you."* The calibration binary read/write is just I/O at the edges;
the value is in the **physics-informed model** that powers two capabilities.

**Two capabilities:**
1. **Diagnose** — read a log and explain *where and why* performance is being left on the
   table (knock-limited spark, boost deviation vs target, over-rich/inefficient fueling).
   Useful on its own; **ships first**.
2. **Optimize** — propose calibration changes that recover that performance, within hard
   safety limits.

**Real-time, phased (D7):** v1 analyzes *recorded* logs **offline**. A **live/streaming
on-vehicle** path is a deliberately separate later track — it needs a low-latency,
embedded redesign and cannot carry the heavy physics+ML on-device, so it is not a v1
feature.

The long-term goal is **custom tuning**: the user states a goal (peak power, broad
torque, spool, fuel economy, a weighted blend) and the system proposes a calibration
that achieves it within safety limits. **v1 deliberately fixes the goal to steady-state
peak power** to keep the first build tractable, while architecting the goal as a
pluggable objective so later goals slot in without redesign.

### Why "AI-assisted" / physics-informed

A pure data-driven model trained on scraped logs fails here: the labeled data it would
need — `(calibration change → measured outcome)` pairs — barely exists. Instead we
encode the **laws of physics** as the model's backbone (a differentiable engine model),
use real data to correct its residuals, and let the model *reason about cause and effect*
rather than memorize correlations. This is what makes it generalize across engines and
extrapolate sensibly.

---

## 2. Goals & non-goals (v1)

### Goals
- Ingest and normalize real ECU **data logs** (wide-open-throttle pulls first).
- **Diagnose** performance bottlenecks from a log — knock-limited regions, boost
  deviation vs target, over-rich/inefficient fueling — as a standalone, human-readable
  report. *(First user-facing deliverable.)*
- A **differentiable mean-value engine model** that predicts, at WOT steady state:
  brake torque/power, lambda, knock margin, and EGT as functions of calibration +
  operating conditions.
- **Calibrate** that model's parameters/residuals against real WOT logs for one platform.
- **Quantify uncertainty** on predictions, with an explicit **validation protocol** (§9.5).
- A **constrained optimizer** that proposes spark / boost / fuel-target changes to
  increase peak power, respecting hard safety limits.
- **Advisory output**: a human-readable change report + per-recommendation confidence.

> **Note on scope honesty:** the v1 core works on calibration **tables** loaded from
> CSV/synthetic, not a real ECU `.bin`. v1 is therefore a **methodology demonstrator**,
> not yet a tuner-ready tool. Binary **read** (real maps in) is the very next milestone
> (M8); binary **write/flash** is later and gated.

### Non-goals (explicitly out of scope for v1)
- ❌ **Live / streaming on-vehicle analysis** — planned as a separate later track (D7), not v1.
- ❌ Writing flashable `.bin` files / closing the loop onto a real ECU (later, gated).
- ❌ Transient / spool / drivability objectives (later).
- ❌ User-defined arbitrary goals (architected for via a goal-spec layer, not built).
- ❌ Multi-platform generalization at once (build one, design for two).
- ❌ Any emissions-control-defeat functionality (permanently out of scope).
- ❌ High-fidelity 1D/3D combustion or CFD as a runtime dependency.

---

## 3. Design principles

1. **Gray-box, not black-box.** Physics provides structure; data corrects residuals.
   A medium-fidelity model *calibrated to real data* beats an uncalibrated high-fidelity
   one for this task — and is far cheaper to run and interrogate.
2. **Differentiable everywhere.** The engine model is written in an autodiff framework so
   we can (a) fit it by gradient descent and (b) **optimize the calibration by
   backpropagating through it**. This is the linchpin that makes "physics-informed
   inverse" stable.
3. **Right-sized fidelity.** We do not chase absolute accuracy. For optimization what
   matters is correct *direction & relative magnitude* of `∂performance/∂param` and
   correct *constraint boundaries* (knock onset, lean limit, EGT/boost ceilings).
4. **Safety is a constraint, not a filter.** Hard limits enter the optimizer's
   constraint set, not a post-hoc clamp bolted on the end.
5. **Uncertainty-aware & advisory.** Every recommendation carries a confidence estimate;
   low-confidence regions are flagged for real-world validation rather than trusted.
6. **Human- and dyno-in-the-loop.** Output is a recommendation for a human to validate;
   real logs feed back to shrink model error (closed improvement loop).
7. **Platform-parameterized.** Engine-specific behavior lives in a parameter set
   (displacement, CR, turbo map, injector size, VE characteristics), so the *same*
   physics core serves N55 and EA888.
8. **Diagnose before optimize.** A trustworthy explanation of *why* performance is lost is
   a prerequisite (and a standalone deliverable) for proposing changes.

---

## 4. Decisions to date

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Data strategy | **Simulator-first**; real WOT logs as anchor | Paired `(change→outcome)` data is scarce online; a sim gives unlimited labeled data and ground truth. |
| D2 | Simulator | **Differentiable Python mean-value model (gray-box)** | Cheap, fast, interrogable, differentiable; accuracy fixed by anchoring to real data, not by buying a commercial sim. |
| D3 | Model + inversion | **Physics-informed forward model, inverted via optimization** | A pure inverse PINN is unstable; a differentiable forward model + optimize-through-it gives the same "inverse" capability, stably. |
| D4 | Objective (v1) | **Steady-state peak power (WOT)** | Easiest regime to model; richest real data; clear success metric. Goal is pluggable for later. |
| D5 | Platforms | **BMW N55, VAG EA888** | Abundant WOT logs/tunes online; well-documented; turbocharged DI engines that exercise the interesting physics (boost, knock). |
| D6 | Output mode | **Advisory + confidence; no auto-flash in v1** | Manages sim-to-real risk and legal/safety exposure. |
| D7 | Real-time scope | **Offline log analysis first; live/streaming on-vehicle as a separate later track** | Heavy physics+ML is feasible offline; live needs an embedded low-latency redesign. |
| D8 | Diagnostics | **First-class deliverable — own module + milestone, before the optimizer** | Directly serves the "evaluate bottlenecks" goal; ships value and trust early. |
| D9 | v1 platform | **EA888 (MK7 GTI/Golf R)** | M0.5 scan: richest, most standardized log channel set (air-mass/stroke, AFR + setpoint, per-cyl knock retard) for model calibration. N55/datazap kept as secondary. See `data-feasibility.md`. |

ADRs for any later reversals go in `docs/decisions/`.

---

## 5. System architecture

```
                          ┌───────────────────────────────────────────────┐
                          │                 DATA LAYER                     │
   real WOT logs ───────▶ │  ingest → normalize → QA → unified log schema  │
   (forums/dyno/sim)      └───────────────────────┬───────────────────────┘
                                                  ▼
        ┌──────────────────────────────────────────────────────────────────────┐
        │                    PHYSICS CORE (differentiable MVEM)                  │
        │  air path · speed-density VE · combustion/torque · Livengood–Wu knock  │
        │  parameters θ_phys (η_vol, turbo eff, FMEP, knock consts, ...)          │
        └───────────────┬──────────────────────────────────────────────────────┘
                        │ CALIBRATION: fit θ_phys + residual nets to real logs
                        ▼
        ┌──────────────────────────────┐
        │  PHYSICS-INFORMED FORWARD     │  perf = f(calibration, conditions)
        │  MODEL  (+ uncertainty σ)     │  torque, λ, knock margin, EGT
        └──────┬──────────────────┬────┘
               │                  │ differentiable
               ▼                  ▼
   ┌────────────────────┐   ┌──────────────────────────────┐   ┌──────────────────────┐
   │  DIAGNOSTICS       │   │  CONSTRAINED OPTIMIZER        │◀──│  SAFETY / LIMITS      │
   │  log → "where/why  │   │  argmax power s.t. limits     │   │  knock margin, λ,     │
   │  perf is lost"     │   │  (optimize THROUGH the model) │   │  EGT/boost, authority │
   └─────────┬──────────┘   └───────────────┬──────────────┘   └──────────────────────┘
             │                              ▼
             │              ┌──────────────────────────────┐
             └─────────────▶│  RECOMMENDATION + EXPLANATION │  deltas, predicted gain,
                            │  + CONFIDENCE REPORT          │  active constraint, per-cell σ
                            └───────────────┬──────────────┘
                                            ▼
                            ┌──────────────────────────────┐
                            │  MAP I/O                      │  read real maps → tables (M8)
                            │  read: M8 · write/flash: later│  write/flash: later, gated
                            └──────────────────────────────┘

   ┌──── new real logs feed back to recalibrate θ_phys (closed improvement loop) ────┐
```

Two consumers hang off the forward model: **diagnostics** (explain) and the **optimizer**
(improve). The dashed-in-spirit MAP I/O block is **deferred** (read in M8, write later).
The feedback edge is the **closed improvement loop**: every new real log can recalibrate
`θ_phys`, shrinking the sim-to-real gap over time.

---

## 6. Component breakdown

| Module | Responsibility | v1? |
|--------|----------------|-----|
| `data` | Log ingestion (CSV/tool exports), channel mapping, unit normalization, QA/outlier rejection, the unified log schema, real-log loaders. | ✅ |
| `physics` | The differentiable mean-value engine model: air path (throttle/turbo/manifold), speed-density VE, combustion/torque, Livengood–Wu knock, EGT estimate. Pure functions of `(state, calibration, conditions, θ_phys)`. | ✅ |
| `calibration` | Gray-box fitting: estimate `θ_phys` and residual-correction networks from real WOT logs; report fit accuracy. | ✅ |
| `model` | The physics-informed **forward** model wrapper, training loop, **uncertainty** (deep ensemble / Bayesian last layer), and the **eval/validation** protocol. | ✅ |
| `diagnostics` | Read a log + the calibrated model → a **bottleneck report**: knock-limited RPM regions, boost deviation vs target, over-rich/inefficient fueling, estimated power left on the table. **First user-facing deliverable.** | ✅ |
| `optimize` | Decision variables, objective, constraint assembly, and the constrained optimizer that backprops through `model`. | ✅ |
| `safety` | Limit definitions (per platform/fuel), constraint functions, validators, sanity checks on proposed deltas (smoothness, authority, monotonicity). | ✅ |
| `maps` | Platform-agnostic calibration **table** representation (axes, scaling, grid). Binary **read** adapters (M8); write/flash adapters later, gated. | table model ✅ · binary read (M8) · write ❌ later |
| `recommend` | Assemble deltas → human-readable report, predicted gains, per-cell confidence, flags. | ✅ |
| `cli` | Command-line entry points orchestrating the above. | ✅ |
| `config` | Pydantic configs; engine **parameter sets** (N55, EA888); run configs; safety-limit sets. | ✅ |

---

## 7. The physics model

A **mean-value engine model (MVEM)**: 0-D, fast, and at v1 evaluated at **steady-state
WOT** across an RPM sweep. Written in an autodiff framework so all parameters are
learnable and gradients flow to the calibration inputs.

> Notation: `p` pressure, `T` temperature, `m_dot` mass flow, `N` engine speed (rev/s),
> `ω` angular speed, `R` gas constant, `γ` ratio of specific heats, `V_d` displacement,
> `n_r` revolutions per cycle (=2 for 4-stroke).

### 7.1 Air path

**Throttle / restriction mass flow** (compressible orifice; at WOT the throttle is open,
but the relation is retained for generality and for the compressor/intercooler path):

```
m_dot = C_d · A(α) · p_us / sqrt(R · T_us) · Ψ(p_ds / p_us)

           sqrt( (2γ/(γ-1)) · (pr^(2/γ) − pr^((γ+1)/γ)) )      if pr  > pr_crit   (subsonic)
Ψ(pr) =
           sqrt(γ) · (2/(γ+1))^((γ+1)/(2(γ-1)))                if pr ≤ pr_crit    (choked)

pr = p_ds / p_us ,   pr_crit = (2/(γ+1))^(γ/(γ-1))
```

**Turbocharger** (compressor draws power, turbine supplies it, wastegate bypasses flow):

```
P_compressor = m_dot_c · cp · T_in  · ( PR_c^((γ−1)/γ) − 1 ) / η_c
P_turbine    = m_dot_t · cp · T_exh · ( 1 − PR_t^(−(γ−1)/γ) ) · η_t
J_tc · dω_tc/dt = (P_turbine − P_compressor) / ω_tc      (→ 0 at steady state)
```

At v1 steady state the shaft balance reduces to an algebraic solve for the operating
boost given wastegate position; transient `J_tc` dynamics are retained in the code but
inactive until the transient milestone.

**Intake-manifold filling** (mass conservation + ideal gas; transient form, steady at v1):

```
dp_im/dt = (R · T_im / V_im) · ( m_dot_in − m_dot_cyl )
```

**Cylinder air flow (speed-density / volumetric efficiency)** — `η_vol` is a key
calibratable map:

```
m_dot_cyl = η_vol(N, p_im) · (p_im · V_d · N) / (R · T_im · n_r)
```

### 7.2 Fueling

```
m_dot_fuel = m_dot_cyl / AFR ,    λ = AFR / AFR_stoich
```

Injector model maps commanded pulse width / target λ to delivered fuel; for power, the
target λ sits in a rich band (~0.78–0.88) for charge cooling and knock suppression — a
**range constraint**, not "as lean as possible."

### 7.3 Combustion & torque

Mean-value indicated torque from fuel energy and a thermal efficiency that depends on
spark timing relative to MBT (and combustion phasing CA50):

```
T_ind   = (m_dot_fuel · Q_LHV · η_comb · η_th(spark, λ, CA50)) / ω
T_brake = T_ind − T_friction(FMEP, N)
P_brake = T_brake · ω
```

Optional crank-angle-resolved burn via a **Wiebe** function (used when we need a pressure
trace for the knock model):

```
x_b(θ) = 1 − exp( −a · ((θ − θ_soc) / Δθ)^(m+1) )
```

### 7.4 Knock — the heart of "ignition timing pull"

**Livengood–Wu autoignition integral** with a Douaud–Eyzat-style ignition-delay
correlation. Knock is predicted when the integral reaches 1 before end of combustion:

```
I_knock = ∫_0^{θ_eoc}  dθ / ( ω · τ(θ) )           knock if  I_knock ≥ 1
τ(θ)   = A · (ON/100)^a · p(θ)^(−n) · exp( B / T(θ) )       (ignition delay)
```

`τ` depends on the in-cylinder pressure/temperature traces, which depend on spark
advance, boost, intake-air temperature, and octane — so this directly yields the
**knock-limited spark advance** the optimizer must respect. The **knock margin**
`(1 − I_knock)` becomes a first-class constraint.

**The hard part — learning *where* the knock limit is.** Real logs overwhelmingly show
knock **avoided**: the ECU has already retarded timing, or the tuner ran conservative
spark, so clean knock-*onset* events are rare. Fitting `(A, a, n, B)` from data that
deliberately stays away from the limit is a **censored / one-sided estimation problem**,
and it is the project's hardest physics-identification task (see §15). Strategy:
1. **Mine logs where the feedback-knock channel is active** — those are observed points
   on (or past) the boundary, i.e. censored boundary samples.
2. **Anchor** `(A, a, n, B)` to published Douaud–Eyzat / SAE correlations and let data
   shift them only modestly (strong prior, small data correction).
3. Keep the **knock-margin constraint conservative**, so any residual model error lands
   on the safe side of the limit.

### 7.5 EGT

An energy-balance estimate of exhaust-gas temperature as a function of λ, spark retard,
and load, used as a **ceiling constraint** (turbo/manifold/valve protection).

### 7.6 Calibratable parameters `θ_phys` (gray-box residuals)

`η_vol(N,p)` map · compressor/turbine efficiencies · `η_comb` · MBT & spark-efficiency
curve · FMEP(N) · knock constants `(A,a,n,B)`. These are fit to real WOT logs in the
`calibration` module; small neural residual terms absorb structurally-unmodeled effects.

> **Data dependency:** compressor/turbine **efficiency maps** for the N55 and EA888 turbos
> may not be publicly available; they will be approximated from geometry and a few known
> operating points, then refined by the log-fit. Tracked as a risk (§15).

---

## 8. Data model & schemas

### 8.1 Unified log schema (normalized)

Heterogeneous tool exports are mapped onto one canonical, unit-normalized schema. Core
channels (missing ones flagged, not fabricated):

| Field | Unit | Notes |
|-------|------|-------|
| `time` | s | monotonic |
| `rpm` | rev/min | |
| `map_kpa` | kPa abs | manifold absolute pressure |
| `boost_kpa` | kPa gauge | derived if only abs present |
| `tps` / `pedal` | % | throttle / pedal |
| `maf_gps` | g/s | if available |
| `lambda_meas` / `afr_meas` | – | wideband; one derived from the other |
| `lambda_target` | – | commanded |
| `ignition_deg` | °BTDC | commanded spark |
| `knock_retard_deg` | ° | feedback knock / spark pull |
| `iat_c`, `ect_c`, `egt_c` | °C | EGT often absent |
| `wastegate_duty` | % | boost actuator |
| `cam_intake_deg`, `cam_exhaust_deg` | ° | VANOS (BMW) / cam phasing (VAG) |
| `injector_dc` | % | duty cycle |
| `gear`, `vehicle_speed` | –, km/h | for WOT-pull detection |

**Run metadata:** vehicle/engine id, hardware mods, **fuel octane**, ambient `p`/`T`,
datalogger/tool, and log source/provenance.

### 8.2 Calibration table representation (platform-agnostic)

```
Table  = { name, x_axis[], y_axis[], x_units, y_units, value_units,
           scaling, grid[ny][nx], metadata }
Calibration = { engine_id, tables: {name → Table}, metadata }
```

Binary formats (XDF / RomRaider-def / proprietary) are handled by **adapters** that read
into / write out of this neutral representation — so the model never touches raw bytes.
**Read** adapters arrive in M8; **write/flash** is later and gated. The v1 core works on
tables loaded from CSV/synthetic.

### 8.3 Operating point

`(rpm, p_im or boost, iat, ect, octane, λ_target, spark, wastegate, cam)` → the model's
input vector; outputs `(torque, power, λ, I_knock / knock margin, egt, σ)`.

---

## 9. The learning approach

### 9.1 Physics-informed forward model

The forward model is the **differentiable MVEM itself**, with:
- **Learnable physical parameters** `θ_phys` (Section 7.6), and
- **Small residual networks** that correct structurally-unmodeled effects, constrained to
  stay small (so physics dominates and extrapolation stays sane).

### 9.2 Training / calibration loss

```
L = L_data            (predicted vs measured torque/λ/knock on real WOT logs)
  + λ_phys · L_phys   (governing-equation residuals at collocation points)
  + λ_reg  · L_reg    (keep residual nets small; smoothness/monotonicity priors)
```

`L_phys` is what makes it a **PINN-style** model: the conservation/flow/knock equations
enter the loss as soft constraints, so the model stays physically consistent even where
data is sparse. This is the data-efficiency antidote to scarce real data.

### 9.3 Uncertainty quantification

**Deep ensemble** (a handful of independently-fit models) as the v1 default — simple,
robust predictive variance. Bayesian last-layer / MC-dropout are alternatives. The
optimizer, the diagnostics, and the report all consume `σ`; high-`σ` cells are flagged
for dyno validation rather than trusted.

### 9.4 Why this is "physics-informed inverse" — done stably

The chosen "inverse" capability is realized **not** by a network that emits map deltas
directly (unstable), but by making the forward model differentiable and **optimizing the
calibration through it** (Section 10). Same outcome, stable training.

### 9.5 Validation & evaluation

Trust is earned *without* a dyno via an explicit protocol — this is how we know the model
is good enough to act on:
- **Held-out logs:** fit on a subset of WOT logs, evaluate on unseen ones (and unseen
  cars where possible).
- **Metrics:** torque/power MAE & relative error; boost prediction error; λ error; and
  **knock-event classification** — does the model flag the RPM regions where the log
  shows knock feedback?
- **Back-test against expert tunes:** where a known-good before/after tune exists, check
  that the optimizer's recommended *direction and locations* agree with what an
  experienced tuner actually changed. **Directional agreement is the bar**, not a
  cell-exact match.
- **Physical sanity checks:** e.g. a spark sweep vs torque shows a single MBT peak;
  enrichment reduces `I_knock`; more boost raises both power and knock tendency.
- **Dyno (when available):** spot-validate only the highest-confidence recommendations.

---

## 10. The optimization formulation

### 10.1 Decision variables
Deltas to selected calibration tables over the WOT operating region:
- spark-advance map `Δspark(N, load)`
- boost target / wastegate map `Δboost(N)`
- fuel/λ-target map `Δλ_tgt(N, load)`

(v1 keeps cam/VANOS fixed; can be added as variables later.)

### 10.2 Objective (v1)

```
maximize   P_peak = max_N  P_brake(N ; calibration)        (steady-state WOT)
```

implemented as a smooth surrogate over the top-end RPM band so gradients are well-behaved.

**Baseline / reference.** "Increase" is always measured against an **explicit reference
calibration** — by default the calibration present in the input log (which may itself be
already modified), or a declared stock map. The reference is recorded with every
recommendation, so the reported "gain" is unambiguous.

**Pluggable for custom tuning (G5).** The objective is a **pluggable interface**; later
goals (AUC torque, spool, fuel economy, user-weighted blends) implement it. User-defined
goals enter through a thin **goal-spec layer** above this interface that translates a
stated goal + weights into the objective and any extra constraints.

### 10.3 Constraints (hard, from `safety`)

```
knock margin:   1 − I_knock(N)        ≥  m_knock           ∀N
lean limit:     λ(N)                  ∈  [λ_min, λ_max]     (rich power band)
EGT ceiling:    egt(N)                ≤  egt_max
boost ceiling:  boost(N)              ≤  boost_max(hardware)
spark authority: spark ∈ [spark_min, spark_max], |Δspark| ≤ slew
table sanity:   smoothness / monotonicity of resulting maps
```

### 10.4 Method
Gradient-based constrained optimization **through the differentiable model**
(projected-gradient / augmented-Lagrangian / SLSQP). Black-box fallbacks (CMA-ES,
Bayesian optimization) are available for any non-differentiable component. Because the
model is differentiable, gradient methods are the efficient default.

### 10.5 Output
Per-table cell deltas, **predicted power gain** with uncertainty, the **active
constraint** at each RPM (e.g., "knock-limited above 5500 rpm"), and a **confidence flag**
per cell. This is what the `recommend` module renders for human review.

---

## 11. Tech stack

| Concern | Choice | Why |
|---------|--------|-----|
| Language | **Python 3.11+** | ecosystem for numerics + ML. |
| Autodiff / differentiable physics | **PyTorch** (primary) with `torchdiffeq` for ODEs; **JAX + diffrax** noted as an alternative | need gradients through the engine model; ensembles are easy. |
| Numerics / data | numpy, scipy, pandas, pyarrow | |
| Optimization | `scipy.optimize`, custom gradient loops; optional **BoTorch/Ax** (Bayesian), **pycma** (CMA-ES) | gradient-first, black-box fallback. |
| Config | **pydantic** + YAML | typed engine/run/safety configs. |
| CLI | **typer** | ergonomic commands. |
| Binary parsing (M8+) | **construct** / kaitai; XDF/RomRaider-style defs | neutral table adapters. |
| API/UI (later) | FastAPI (+ thin web UI) | |
| Testing / quality | **pytest**, ruff, mypy | |
| Plotting | matplotlib / plotly | dyno curves, table heatmaps. |
| Experiment tracking | MLflow (optional) | calibration runs reproducible. |
| Packaging | `pyproject.toml` (uv or poetry) | |

---

## 12. Safety, legal & ethics

- **Intended use:** off-road / track / dyno / research. Not for evading regulations.
- **Advisory by default:** v1 emits recommendations only; **no flashing**. Any future
  flashable output is a separately-gated milestone behind explicit human review.
- **Safety as constraints:** knock margin, λ floor, EGT and boost ceilings, and spark
  authority are *hard* constraints in the optimizer — not post-hoc suggestions.
- **Uncertainty surfaced:** low-confidence recommendations are flagged for dyno
  validation, never silently trusted.
- **No defeat devices:** no functionality to disable or spoof emissions controls
  (catalysts, EGR, DPF/GPF, O2/closed-loop). Permanently out of scope.
- **Provenance:** training-data sources are recorded; we respect the terms of any data
  source we use.

---

## 13. Repository layout

```
project/
├── README.md
├── pyproject.toml                 # (added at scaffold time)
├── docs/
│   ├── ARCHITECTURE.md            # this document
│   └── decisions/                 # ADRs for later reversals
├── src/dynamis/
│   ├── data/                      # ingestion, schema, normalization, QA, loaders
│   ├── physics/                   # differentiable MVEM: airpath, vol_eff, combustion, knock, egt
│   ├── calibration/               # gray-box fit of θ_phys + residuals to real logs
│   ├── model/                     # physics-informed forward model, training, uncertainty, eval
│   ├── diagnostics/               # log → bottleneck report (knock-limited, boost dev, fueling)
│   ├── optimize/                  # objective, constraints, constrained optimizer
│   ├── safety/                    # limit sets, constraint fns, validators
│   ├── maps/                      # table representation; binary READ (M8); write later
│   ├── recommend/                 # report assembly, explanations, confidence
│   ├── cli/                       # typer entry points
│   └── config/                    # pydantic configs; engine param sets (n55, ea888)
├── configs/                       # YAML engine/run/safety configs
├── data/                          # raw/ interim/ processed/  (gitignored)
├── notebooks/                     # exploration
├── tests/
└── scripts/
```

---

## 14. Roadmap & milestones

| ID | Milestone | Deliverable |
|----|-----------|-------------|
| **M0** | Architecture & scaffold | This doc ✅ · repo skeleton + tooling |
| **M0.5** | **Data feasibility spike** ⛔gate | Assemble a clean, labeled WOT corpus (octane / mods / ambient) for N55/EA888. **Go/no-go gate** for the whole data-anchored approach — if clean data can't be gathered, we replan before building further. |
| **M1** | Data layer | Unified log schema; ingest + QA of the corpus |
| **M2** | Differentiable MVEM v0 | Steady-state WOT forward model; qualitative sanity vs known trends |
| **M3** | Calibration | Fit `θ_phys` + residuals to real WOT logs; report accuracy & error bars |
| **M4** | Forward model + uncertainty | Physics-informed model with deep-ensemble σ; **validation protocol (§9.5)** in place |
| **M5** | **Diagnostics** | Log → bottleneck report (knock-limited regions, boost deviation, over-rich fueling, power left on table). **First user-facing deliverable.** |
| **M6** | Inverse optimizer | Constrained peak-power optimization; spark/boost/λ deltas + confidence |
| **M7** | Reporting / CLI | End-to-end on one platform; advisory report + table diff |
| **M8** | **Binary map read** | Parse real calibrations into the neutral table model (read-only; **no flashing**) so recommendations map onto real breakpoints |
| **L1+** | Later | transient/spool objective · user-defined goals (goal-spec layer) · binary **write/flash** (gated) · **live/streaming on-vehicle track (D7)** · multi-platform · closed-loop refinement from new logs |

---

## 15. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Real-data acquisition** (can't assemble a clean labeled WOT corpus) | High | High | **M0.5 feasibility spike as a go/no-go gate**; pursue multiple sources; the sim can pre-train, but anchoring needs real logs — so this gates everything. |
| **Knock-limit identification** (censored data) | High | High | Strategy in §7.4: mine feedback-knock-active logs as boundary samples, anchor `(A,a,n,B)` to published correlations, keep knock margin conservative. |
| **Sim-to-real gap** | High | High | Anchor model to real WOT data; advisory + dyno validation; quantified uncertainty; closed improvement loop. |
| **Data noise / inconsistency** | High | Med | Rigorous QA; canonical schema; flag-don't-fabricate missing channels; PINN physics loss for data-efficiency. |
| **PINN / inverse instability** | Med | Med | Forward-model + optimize-through-it instead of direct inverse net; keep residual nets small. |
| **Turbo efficiency-map data unavailable** | Med | Low–Med | Approximate from geometry + known points; refine via log-fit (§7.6). |
| **Platform variance** | Med | Med | Physics parameterized per engine; one core, swappable param sets. |
| **Misuse / unsafe flash** | Low (v1) | High | No flashing in v1; hard constraints; human-in-loop; no defeat features. |
| **Compute for training** | Med | Low | MVEM is cheap; ensembles are small; steady-state v1 keeps cost modest. |

---

## 16. Open questions

1. ~~Which platform first~~ — **RESOLVED (D9): EA888 (MK7 GTI/Golf R)** via the M0.5 scan
   (`data-feasibility.md`).
2. **Fuel assumptions** — which octane / ethanol-content cases to model first (e.g. 93
   pump vs E30/E85)? Strongly affects the knock constraint.
3. **Real-log sources** — which forums/dyno datasets/loggers, and their terms of use.
4. **Decision variables in v1** — spark + boost + λ only, or include cam/VANOS?
5. **Compute budget** — local GPU vs cloud for calibration/ensembles.
6. **Validation partner** — is a dyno or a known-good reference tune available to check
   M5/M6 output against? (Drives the §9.5 back-test.)

*Resolved this revision:* real-time scope (D7 — offline first, live later) and
diagnostics as a first-class deliverable (D8).

---

## 17. Glossary

- **MVEM** — Mean-Value Engine Model; 0-D physics model of cycle-averaged behavior.
- **VE / `η_vol`** — Volumetric efficiency; how completely the cylinder fills.
- **MBT** — Minimum spark advance for Best Torque.
- **CA50** — Crank angle of 50% mass-fraction-burned (combustion phasing).
- **Livengood–Wu** — Autoignition integral predicting knock onset.
- **FMEP** — Friction Mean Effective Pressure (engine friction term).
- **PINN** — Physics-Informed Neural Network.
- **WOT** — Wide-Open Throttle.
- **EGT** — Exhaust Gas Temperature.
- **VANOS** — BMW variable cam timing (analogous to VAG cam phasing).
- **Censored data** — observations where the true value is only known to lie past a
  threshold (here: we mostly see knock *avoided*, not knock *onset*).
```
