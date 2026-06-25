"""Tests for the curated corpus (add/validate/load)."""

from __future__ import annotations

import pandas as pd

from dynamis.data.corpus import (
    CorpusMeta,
    Fuel,
    Source,
    Vehicle,
    add_log,
    load_corpus,
    validate_metadata,
)
from dynamis.data.synthetic import generate_cobb_wot_log


def _good_meta(entry_id="test01"):
    return CorpusMeta(
        entry_id=entry_id,
        source=Source(type="own_car", consent="self"),
        vehicle=Vehicle(model="MK7 GTI", turbo="IS20"),
        fuel=Fuel(octane_ron=98.0),
        mods=["intake", "downpipe"],
    )


def test_add_and_load_corpus(tmp_path):
    csv = tmp_path / "log.csv"
    generate_cobb_wot_log(seed=11).to_csv(csv, index=False)
    corpus = tmp_path / "corpus"

    res = add_log(str(csv), _good_meta(), corpus_dir=str(corpus))
    assert res.ok
    assert res.qa["wot_segments"] >= 1
    assert res.warnings == []  # full metadata -> no warnings

    entries = load_corpus(str(corpus))
    assert len(entries) == 1
    assert entries[0].meta.fuel.octane_ron == 98.0
    assert entries[0].meta.vehicle.turbo == "IS20"
    assert (corpus / "index.yaml").exists()


def test_rejects_non_wot_log(tmp_path):
    df = pd.DataFrame(
        {
            "Time": [0.0, 0.1, 0.2],
            "Engine Speed": [820, 815, 810],
            "Intake Manifold Pressure": [14.2, 14.1, 14.2],
            "AFR": [14.7, 14.7, 14.7],
            "Accel Pedal Position": [4, 5, 4],
        }
    )
    csv = tmp_path / "idle.csv"
    df.to_csv(csv, index=False)
    res = add_log(str(csv), _good_meta("idle01"), corpus_dir=str(tmp_path / "corpus"))
    assert not res.ok
    assert any("WOT" in p for p in res.problems)


def test_validate_warns_on_missing_context():
    warns = validate_metadata(CorpusMeta(entry_id="bare"))
    joined = " ".join(warns).lower()
    assert "octane" in joined
    assert "turbo" in joined


def test_metadata_yaml_roundtrip(tmp_path):
    import yaml

    meta = _good_meta("rt01")
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(meta.to_dict()))
    back = CorpusMeta.from_yaml(str(p))
    assert back.entry_id == "rt01"
    assert back.fuel.octane_ron == 98.0
    assert back.mods == ["intake", "downpipe"]
