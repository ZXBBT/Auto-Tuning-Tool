# Licensed Public Dataset Assessment

**Status:** Preliminary — automated inspection blocked · **Date:** 2026-06

> Part of the M0.5 follow-up (data sourcing option 2). **Bottom line:** neither public
> dataset is a confirmed fit for *calibration*; one is a candidate for *power validation*.
> Full confirmation needs a manual download (Kaggle account), which the curation helper
> (`data/corpus.py`) can then ingest and assess concretely.

## What blocked a full assessment

- **dyno.cobbtuning.com / cobbtuning.com/dyno-database** → HTTP **403 Forbidden** to automated fetch.
- **kaggle.com/datasets/...** → reCAPTCHA / JS-rendered; only the page title is retrievable.

So the notes below are from prior knowledge + search snippets, not direct inspection.

## 1. Kaggle — "COBB Tuning – Dyno Data" (paxtonjacob, ~4,952 runs)

- **What it is:** a scrape/export of COBB's public **dyno results** database — i.e.
  **power/torque outcomes** per run, with vehicle + (some) modification context.
- **Role for us:** **NOT calibration data** — it is dyno *results*, not per-channel
  time-series logs, so it can't fit the MVEM. But it is a strong candidate for the thing
  we still lack: a **measured-power source for validation** (ARCHITECTURE open-Q #6,
  §9.5 absolute-power back-test).
- **Open question:** does it include **VW/Audi EA888** (MK7 GTI / Golf R / Audi S3/A3)?
  COBB sells Accessports for these, so coverage is *plausible* but unconfirmed.
- **Caveat:** dyno DB entries may be peak HP/TQ + curve only, possibly without the boost/
  fuel/timing context needed to use them rigorously.

## 2. Kaggle — "Car ECU Datalogs" (gxkok21)

- **What it is:** unconfirmed. The generic name suggests OBD-II / ECU logs from some
  vehicle(s); platform and channel set are unknown.
- **Role for us:** can't confirm EA888 relevance without inspection. Likely **not**
  EA888-specific; treat as low-confidence until inspected.

## Recommendation

1. **COBB Dyno Data** — worth a manual download to check for EA888 coverage; if present,
   adopt as a **power-validation** set (not calibration). Tag it `source.type: dataset`.
2. **Car ECU Datalogs** — download and inspect; only adopt if it actually contains EA888
   WOT logs with the channels in ARCHITECTURE §8.1.
3. Either way: **drop the CSVs in and run the curation helper** —
   `scripts/add_log_to_corpus.py <file.csv> <metadata.yaml>` — which validates channels +
   units + WOT presence and reports whether the data is actually usable. That turns this
   from guesswork into a concrete per-file verdict.

## Sources

- [Kaggle — COBB Tuning Dyno Data](https://www.kaggle.com/datasets/paxtonjacob/cobb-tuning-dyno-data)
- [Kaggle — Car ECU Datalogs](https://www.kaggle.com/datasets/gxkok21/car-ecu-datalogs)
- [COBB Dyno Database](https://dyno.cobbtuning.com/)
