"""Tests for the CLI (torch-free commands). Skipped if typer isn't installed."""

from __future__ import annotations

import pytest

pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from dynamis.cli.main import app  # noqa: E402

runner = CliRunner()


def test_make_synthetic_ingest_diagnose(tmp_path):
    log = tmp_path / "log.csv"
    r = runner.invoke(app, ["make-synthetic", "--out", str(log), "--spark-offset", "-4", "--seed", "3"])
    assert r.exit_code == 0, r.output
    assert log.exists()

    r2 = runner.invoke(app, ["ingest", str(log)])
    assert r2.exit_code == 0
    assert "wot_segments" in r2.output

    r3 = runner.invoke(app, ["diagnose", str(log)])
    assert r3.exit_code == 0
    assert "Diagnostic report" in r3.output
    assert "available" in r3.output  # conservative tune -> timing headroom finding


def test_add_log_via_cli(tmp_path):
    log = tmp_path / "log.csv"
    runner.invoke(app, ["make-synthetic", "--out", str(log), "--seed", "1"])
    meta = tmp_path / "m.yaml"
    meta.write_text(
        "entry_id: cli_test\nfuel:\n  octane_ron: 98\nvehicle:\n  turbo: IS20\nmods:\n  - stock\n"
        "source:\n  type: dataset\n  consent: self\n"
    )
    r = runner.invoke(app, ["add-log", str(log), str(meta), "--corpus-dir", str(tmp_path / "corpus")])
    assert r.exit_code == 0
    assert "ADDED" in r.output
    assert (tmp_path / "corpus" / "cli_test" / "log.csv").exists()
