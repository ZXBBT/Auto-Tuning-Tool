# Project Dynamis — Architecture

**Status:** Draft for review · **Version:** 0.1 · **Scope:** v1 design

> This document is the single source of truth for *what we are building and why*,
> before any code is written. It is intentionally detailed so the design can be
> reviewed and corrected up front. Working codename **Dynamis**; rename freely.

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
the value is in the **physics-informed model + a constrained optimizer**.

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
- A **differentiable mean-value engine model** that predicts, at WOT steady state:
  brake torque/power, lambda, knock margin, and EGT as functions of calibration +
  operating conditions.
- **Calibrate** that model's parameters/residuals against real WOT logs for one platform.
- **Quantify uncertainty** on predictions.
- A **constrained optimizer** that proposes spark / boost / fuel-target changes to
  increase peak power, respecting hard safety limits.
- **Advisory output**: a human-readable change report + per-recommendation confidence.

### Non-goals (explicitly out of scope for v1)
- ❌ Writing flashable `.bin` files / closing the loop onto a real ECU (later, gated).
- ❌ Transient / spool / drivability objectives (later).
- ❌ User-defined arbitrary goals (architected for, not built).
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

ADRs for any later reversals go in `docs/decisions/`.

---

## 5. System architecture

```
                          ┌───────────────────────────────────────────────┐
                          │                 DATA LAYER                     │
   real WOT logs ───────▶ │  ingest → normalize → QA → unified log schema  │
   (forums/dyno/sim)      └───────────────────────┬───────────────────────┘
                                                  │ calibration data
                                                  ▼
        ┌──────────────────────────────────────────────────────────────────────┐
        │                    PHYSICS CORE (differentiable MVEM)                  │
        │  air path · speed-density VE · combustion/torque · Livengood–Wu knock  │
        │  parameters θ_phys (η_vol, turbo eff, FMEP, knock consts, ...)          │
        └───────────────┬──────────────────────────────────────────┬────────────┘
                        │ (1) CALIBRATION: fit θ_phys + residual nets to real logs │
                        ▼                                                          │
        ┌──────────────────────────────┐                                          │
        │  PHYSICS-INFORMED FORWARD     │  perf = f(calibration, conditions)       │
        │  MODEL  (+ uncertainty)       │  torque, λ, knock margin, EGT, + σ        │
        └───────────────┬──────────────┘                                          │
                        │ differentiable                                          │
                        ▼                                                          │
        ┌──────────────────────────────┐     ┌──────────────────────────────┐     │
        │  CONSTRAINED OPTIMIZER        │◀────│  SAFETY / LIMITS              │     │
        │  argmax power s.t. limits     │     │  knock margin, λ floor,       │     │
        │  (optimize THROUGH the model) │     │  EGT/boost ceilings, authority│     │
        └───────────────┬──────────────┘     └──────────────────────────────┘     │
                        ▼                                                          │
        ┌──────────────────────────────┐                                          │
        │  RECOMMENDATION + EXPLANATION │  table deltas, predicted gain, confidence │
        │  + CONFIDENCE REPORT          │  flags low-confidence cells for dyno      │
        └───────────────┬──────────────┘                                          │
                        ▼                                                          │
        ┌──────────────────────────────┐                                          │
        │  MAP I/O  (LATER, gated)      │  apply deltas to calibration tables;      │
        │  binary parse/write + defs    │  human review before any flash            │
        └──────────────────────────────┘                                          │
                        ▲                                                          │
                        └──────── new real logs feed back to recalibrate ──────────┘
```

The dashed feedback edge is the **closed improvement loop**: every new real log the
system sees can recalibrate `θ_phys`, shrinking the sim-to-real gap over time.

---

## 6. Component breakdown

| Module | Responsibility | v1? |
|--------|----------------|-----|
| `data` | Log ingestion (CSV/tool exports), channel mapping, unit normalization, QA/outlier rejection, the unified log schema, real-log loaders. | ✅ |
| `physics` | The differentiable mean-value engine model: air path (throttle/turbo/manifold), speed-density VE, combustion/torque, Livengood–Wu knock, EGT estimate. Pure functions of `(state, calibration, conditions, θ_phys)`. | ✅ |
| `calibration` | Gray-box fitting: estimate `θ_phys` and residual-correction networks from real WOT logs; report fit accuracy. | ✅ |
| `model` | The physics-informed **forward** model wrapper, training loop, and **uncertainty** (deep ensemble / Bayesian last layer). | ✅ |
| `optimize` | Decision variables, objective, constraint assembly, and the constrained optimizer that backprops through `model`. | ✅ |
| `safety` | Limit definitions (per platform/fuel), constraint functions, validators, sanity checks on proposed deltas (smoothness, authority, monotonicity). | ✅ |
| `maps` | Platform-agnostic calibration **table** representation (axes, scaling, grid). Binary parse/write + definition adapters. | table model ✅ · binary I/O ❌ (later) |
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

### 7.5 EGT

An energy-balance estimate of exhaust-gas temperature as a function of λ, spark retard,
and load, used as a **ceiling constraint** (turbo/manifold/valve protection).

### 7.6 Calibratable parameters `θ_phys` (gray-box residuals)

`η_vol(N,p)` map · compressor/turbine efficiencies · `η_comb` · MBT & spark-efficiency
curve · FMEP(N) · knock constants `(A,a,n,B)`. These are fit to real WOT logs in the
`calibration` module; small neural residual terms absorb structurally-unmodeled effects.

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
Binary I/O is a later milestone; v1 works on tables loaded from CSV/synthetic.

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
optimizer and the report both consume `σ`; high-`σ` cells are flagged for dyno
validation rather than trusted.

### 9.4 Why this is "physics-informed inverse" — done stably

The chosen "inverse" capability is realized **not** by a network that emits map deltas
directly (unstable), but by making the forward model differentiable and **optimizing the
calibration through it** (Section 10). Same outcome, stable training.

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
The objective is a **pluggable interface** — later goals (AUC torque, spool, fuel economy,
user-weighted blends) implement the same interface.

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
| Binary parsing (later) | **construct** / kaitai; XDF/RomRaider-style defs | neutral table adapters. |
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
│   ├── model/                     # physics-informed forward model, training, uncertainty
│   ├── optimize/                  # objective, constraints, constrained optimizer
│   ├── safety/                    # limit sets, constraint fns, validators
│   ├── maps/                      # table representation; (later) binary I/O + def adapters
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
| **M1** | Data layer | Unified log schema; ingest + QA of sample WOT logs (N55/EA888) |
| **M2** | Differentiable MVEM v0 | Steady-state WOT forward model; qualitative sanity vs known trends |
| **M3** | Calibration | Fit `θ_phys` + residuals to real WOT logs; report accuracy & error bars |
| **M4** | Forward model + uncertainty | Physics-informed model with deep-ensemble σ |
| **M5** | Inverse optimizer | Constrained peak-power optimization; spark/boost/λ deltas + confidence |
| **M6** | Reporting / CLI | End-to-end on one platform; advisory report + table diff |
| **L1+** | Later | transient/spool objective · user-defined goals · binary map I/O (gated) · multi-platform · closed-loop refinement from new logs |

---

## 15. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Sim-to-real gap** | High | High | Anchor model to real WOT data; advisory + dyno validation; quantified uncertainty; closed improvement loop. |
| **Data scarcity / noise** | High | Med | Focus on abundant WOT logs; rigorous QA; PINN physics loss for data-efficiency; synthetic augmentation from the sim. |
| **PINN / inverse instability** | Med | Med | Forward-model + optimize-through-it instead of direct inverse net; keep residual nets small. |
| **Platform variance** | Med | Med | Physics parameterized per engine; one core, swappable param sets. |
| **Knock model fidelity** | Med | High | Calibrate knock constants to real knock/feedback data; conservative knock-margin constraint. |
| **Misuse / unsafe flash** | Low (v1) | High | No flashing in v1; hard constraints; human-in-loop; no defeat features. |
| **Compute for training** | Med | Low | MVEM is cheap; ensembles are small; steady-state v1 keeps cost modest. |

---

## 16. Open questions

1. **Which platform first** — N55 vs EA888 — decided by **whose WOT-log dataset we can
   assemble most cleanly**. (Needs a data-availability scan in M1.)
2. **Fuel assumptions** — which octane / ethanol-content cases to model first (e.g. 93
   pump vs E30/E85)? Strongly affects the knock constraint.
3. **Real-log sources** — which forums/dyno datasets/loggers, and their terms of use.
4. **Decision variables in v1** — spark + boost + λ only, or include cam/VANOS?
5. **Compute budget** — local GPU vs cloud for calibration/ensembles.
6. **Validation partner** — is a dyno or a known-good reference tune available to check
   M5 output against?

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
