"""Dynamis CLI — ties the pipeline together.

torch is imported lazily inside `train`/`optimize`, so `ingest`, `diagnose`,
`make-synthetic`, and `add-log` work without PyTorch installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Dynamis — physics-informed ECU calibration analysis & optimization.", no_args_is_help=True)


@app.command()
def ingest(log: Path = typer.Argument(..., help="raw log CSV")):
    """Ingest a log into the canonical schema and print a QA report."""
    from dynamis.data import COBB_EA888, load_csv, qa_report

    lf = load_csv(str(log), profile=COBB_EA888)
    typer.echo(json.dumps(qa_report(lf), indent=2, default=str))


@app.command()
def diagnose(
    log: Path = typer.Argument(..., help="raw log CSV"),
    octane: float = typer.Option(98.0, help="fuel RON (knock model)"),
):
    """Diagnose a log for performance bottlenecks."""
    from dynamis.data import COBB_EA888, load_csv
    from dynamis.diagnostics import diagnose as run_diagnose

    lf = load_csv(str(log), profile=COBB_EA888)
    typer.echo(run_diagnose(lf, octane=octane).render())


@app.command("make-synthetic")
def make_synthetic(
    out: Path = typer.Option(Path("data/synthetic/ea888_sample_wot.csv"), help="output CSV"),
    spark_offset: float = typer.Option(0.0, help="<0 simulates a conservative tune"),
    seed: int = typer.Option(0),
):
    """Generate a synthetic COBB-style EA888 WOT log (for trying the tool)."""
    from dynamis.data import generate_cobb_wot_log

    out.parent.mkdir(parents=True, exist_ok=True)
    df = generate_cobb_wot_log(seed=seed, spark_offset_deg=spark_offset)
    df.to_csv(out, index=False)
    typer.echo(f"wrote {out} ({len(df)} rows)")


@app.command("add-log")
def add_log_cmd(
    log: Path = typer.Argument(..., help="raw log CSV"),
    metadata: Path = typer.Argument(..., help="metadata YAML (see configs/metadata_template.yaml)"),
    corpus_dir: Path = typer.Option(Path("data/corpus")),
    force: bool = typer.Option(False, help="add even if QA finds problems"),
):
    """Validate a real log and file it into the curated corpus."""
    from dynamis.data.corpus import CorpusMeta, add_log

    meta = CorpusMeta.from_yaml(str(metadata))
    res = add_log(str(log), meta, corpus_dir=str(corpus_dir), force=force)
    typer.echo(json.dumps(res.qa, indent=2, default=str))
    for w in res.warnings:
        typer.echo(f"warning: {w}")
    for p in res.problems:
        typer.echo(f"problem: {p}")
    typer.echo("ADDED" if res.ok else "NOT ADDED (re-run with --force)")
    raise typer.Exit(0 if res.ok else 1)


@app.command()
def train(
    out: Path = typer.Option(Path("models/surrogate.pt"), help="where to save the ensemble"),
    n: int = typer.Option(3000, help="training samples"),
    epochs: int = typer.Option(800),
    k: int = typer.Option(5, help="ensemble size"),
):
    """Train the surrogate ensemble on sim data and save it."""
    from dynamis.model.data import make_dataset
    from dynamis.model.ensemble import DeepEnsemble
    from dynamis.model.surrogate import best_device

    typer.echo(f"device: {best_device()}; training k={k} on {n} sim samples...")
    ens = DeepEnsemble(k=k).fit(make_dataset(n=n), epochs=epochs)
    out.parent.mkdir(parents=True, exist_ok=True)
    ens.save(str(out))
    typer.echo(f"saved {out}")


@app.command()
def optimize(
    model: Path = typer.Option(Path("models/surrogate.pt"), help="trained ensemble (trains a quick one if absent)"),
    octane: float = typer.Option(98.0),
    charge_temp: float = typer.Option(50.0, help="charge air temp [degC]"),
    boost_max: float = typer.Option(1.8, help="boost ceiling [bar]"),
    knock_margin: float = typer.Option(0.10, help="minimum knock margin"),
):
    """Optimize a WOT calibration (spark/boost/lambda) within the safety limits."""
    from dynamis.model.data import make_dataset
    from dynamis.model.ensemble import DeepEnsemble
    from dynamis.optimize import SafetyLimits, optimize_sweep

    if model.exists():
        ens = DeepEnsemble.load(str(model))
        typer.echo(f"loaded {model}")
    else:
        typer.echo(f"{model} not found; training a quick surrogate (run `dynamis train` to persist one)...")
        ens = DeepEnsemble(k=3).fit(make_dataset(n=1500), epochs=500)

    limits = SafetyLimits(knock_margin_min=knock_margin, boost_max_bar=boost_max)
    res = optimize_sweep(ens, list(range(3000, 6801, 400)), charge_temp_c=charge_temp, octane=octane, limits=limits)
    typer.echo(res.table.to_string(index=False))
    typer.echo(
        f"\npeak {res.peak_power_hp:.0f} hp   baseline {res.baseline_peak_hp:.0f} hp   gain +{res.gain_hp:.0f} hp"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
