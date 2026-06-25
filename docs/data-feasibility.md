# M0.5 — Data Feasibility Scan

**Status:** ✅ Complete · **Gate verdict:** 🟢 GREEN (proceed) · **Date:** 2026-06

> The go/no-go gate for the data-anchored approach (see ARCHITECTURE §14, §15).
> **Outcome: viable.** Real WOT logs with the channels we need exist, in CSV, at volume,
> for both candidate platforms. **v1 platform selected: EA888 (MK7 GTI/Golf R).**

---

## 1. The question

Can we assemble a clean, labeled corpus of wide-open-throttle (WOT) logs to **anchor /
calibrate** the physics model (ARCHITECTURE D1–D2)? And which platform — **BMW N55** or
**VAG EA888** — is the cleaner starting point?

## 2. Method

Web survey of: the mainstream datalogging tools per platform, the channels they expose,
where logs are shared publicly, and any structured public datasets.

## 3. Findings

Both platforms log to **CSV** via mainstream tools and have communities that publicly
share WOT pulls.

| Dimension | **EA888** (MK7 GTI/Golf R · COBB) | **N55** (BMW · MHD / JB4) |
|---|---|---|
| Log format | CSV (Accessport / Accesstuner) | CSV (MHD, JB4) |
| Channel standardization | ★★★★★ fixed COBB monitor list | ★★★☆ varies by tool |
| VE / airflow | **Air Mass Intake Manifold per stroke** ✓ | airflow varies by tool |
| Fueling | **AFR + AFR Set Point** ✓ (measured + target) | AFR bank 1/2 (weaker on stock) |
| Knock | **Per-cylinder Knock Retard (cyl 1–4)** ✓ | per-cyl ignition corrections ✓ |
| Air path | Boost + MAP + IAT + Charge-Air-Temp + **wastegate setpoint** ✓ | boost, IAT |
| Combustion / cam | Ignition Timing Final + intake/exhaust cam ✓ | timing + corrections |
| Where logs live | Forums (mygolfmk7, vwvortex) — scattered | **datazap.me** (central, fuel-tagged) + SpoolStreet / Bimmerpost — high volume |
| Corpus assembly | Moderate (curate across threads) | Easier (centralized, browsable) |

### Public / structured datasets (secondary)
- **Kaggle "Car ECU Datalogs"** — exists; contents/platform unconfirmed.
- **Kaggle "COBB Tuning – Dyno Data"** (~4,950 dyno runs) — potential **power ground-truth**
  for validation; platform coverage unconfirmed (Kaggle wall). Worth a closer look.
- **GitHub** — Simos12/18 editors (Simos18 is the EA888/MQB ECU), MED17/EDC17 checksum
  tools, RomRaider definitions. Relevant later for the binary-read milestone (M8).

## 4. Why EA888 is the stronger calibration substrate

The COBB EA888 channel set maps almost **1:1 onto the MVEM** (ARCHITECTURE §7):

| Log channel | Feeds (model use) |
|---|---|
| Air Mass Intake Manifold **per stroke** | calibrates `η_vol(N, p_im)` (§7.1) — direct VE anchor |
| Boost Pressure + Intake Manifold Pressure | air-path / manifold state (§7.1) |
| IAT + Charge Air Temp | charge temperature → knock & density (§7.1, §7.4) |
| AFR + **AFR Set Point** | fueling `λ` measured & target (§7.2) |
| Injection Time (per cyl) | injector model (§7.2) |
| Ignition Timing Final | spark input to combustion/knock (§7.3, §7.4) |
| **Per-cylinder Knock Retard** | the censored knock-boundary signal (§7.4) |
| Intake / Exhaust Cam Position | cam state (held fixed v1, logged for later) |
| Wastegate Mass Flow Set Point + actuator | boost actuator (§7.1) |
| Engine Speed (RPM) | operating point |

## 5. Caveats / risks (shape how we collect)

1. **No measured power in the logs.** Logs carry airmass / torque-request / physical
   channels — **not crank or wheel HP**. The peak-power objective is *computed* by the
   model; validating **absolute** power needs **dyno data** (Kaggle COBB dyno set, or
   paired dyno+log build threads). → keeps ARCHITECTURE open-question #6 live.
2. **Metadata gaps** — octane, mods, ambient often untagged in the file. → **curate a
   modest anchor set**, don't mass-scrape.
3. **AFR fidelity** from factory sensors is limited at rich WOT.
4. **Terms of use** — user-shared logs; collect a curated set manually and respect source
   terms.

## 6. Decision

**D9 — v1 platform = EA888 (MK7 GTI/Golf R).** N55 / datazap.me retained as a secondary
pool for cross-checking and later multi-platform generalization. Recorded in
ARCHITECTURE §4; resolves open-question #1.

## 7. Implications for next steps

- The sim's engine **parameter set** targets the **EA888 Gen3 2.0T** (≈1984 cc; IS20 turbo
  on GTI / IS38 on Golf R; CR ≈ 9.3–9.6). Exact values pinned in `config/` at build time.
- **Collect a small curated anchor set** of EA888 WOT logs with as much metadata
  (octane, mods, ambient) as can be recovered.
- **Keep hunting a power/dyno validation source** (caveat #1) — gates §9.5 absolute-power
  validation, not the model build itself.

## Sources

- [Interpreting MHD Datalogs (N54/N55) — Boost Monkey](https://boostmonkey.com/blogs/guides/interpreting-mhd-datalogs-n54-n55-335i-135i-535i)
- [MHD N55 — Post your logs (SpoolStreet)](https://spoolstreet.com/threads/mhd-n55-post-your-logs.432/)
- [Datazap.me — interactive datalogs](https://datazap.me/)
- [COBB — Volkswagen (and Audi) Datalog Guide](https://cobbtuning.atlassian.net/wiki/spaces/PRS/pages/252674049/Volkswagen+Datalog+Guide)
- [COBB — Mk7 GTI/Golf R monitor list](https://cobbtuning.atlassian.net/wiki/spaces/PRS/pages/222691360)
- [COBB — VW Mk7 Tuning Guide](https://cobbtuning.atlassian.net/wiki/spaces/PRS/pages/143753246/Volkswagen+Mk7+Tuning+Guide)
- [MK7 GTI Stratified OTS datalog refinement (MyGolfMk7)](https://mygolfmk7.com/2024/02/mk7-gti-stratified-ots-datalog-refinement/)
- [JB4 N55 logging / channels (JB4tech)](https://www.jb4tech.com/forum/model-specific-engine-tuning-modification-discussion/n55/9035-bmw-n55-engine-failures/page2)
- [Kaggle — Car ECU Datalogs](https://www.kaggle.com/datasets/gxkok21/car-ecu-datalogs)
- [Kaggle — COBB Tuning Dyno Data](https://www.kaggle.com/datasets/paxtonjacob/cobb-tuning-dyno-data)
