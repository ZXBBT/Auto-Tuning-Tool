"""Tests for the HTTP API. Skipped if torch or fastapi isn't installed."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("torch")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from dynamis.api import Settings, create_app  # noqa: E402
from dynamis.data import generate_cobb_wot_log  # noqa: E402
from dynamis.model.data import make_dataset  # noqa: E402
from dynamis.model.ensemble import DeepEnsemble  # noqa: E402
from dynamis.telemetry import FRAMES_BY_ID, crc_ok, decode  # noqa: E402


@pytest.fixture(scope="module")
def ensemble():
    return DeepEnsemble(k=2, hidden=(32, 32), device="cpu").fit(make_dataset(n=400, seed=0), epochs=200)


@pytest.fixture(scope="module")
def client(ensemble):
    with TestClient(create_app(Settings(), ensemble=ensemble)) as c:
        yield c


def test_health_and_meta(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["model_loaded"]
    m = client.get("/api/meta").json()
    assert m["model"]["members"] == 2
    assert m["domain"]["rpm"] == [2500.0, 7000.0]
    assert "uncalibrated" in m["caveat"]


def test_sample_analysis(client):
    ids = [s["id"] for s in client.get("/api/samples").json()]
    r = client.get(f"/api/samples/{ids[0]}/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["wot"]["t_end"] > body["wot"]["t_start"]
    assert {f["category"] for f in body["findings"]} >= {"knock", "fueling", "boost", "timing"}
    assert len(body["series"]["rpm"]) == len(body["series"]["time_s"])
    assert client.get("/api/samples/nope/analysis").status_code == 404


def test_upload_analysis_and_bad_input(client, tmp_path):
    csv = generate_cobb_wot_log(spark_offset_deg=-4, seed=1).to_csv(index=False).encode()
    r = client.post("/api/logs/analyze", files={"file": ("pull.csv", csv, "text/csv")}, data={"octane": "95"})
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "pull.csv"

    r = client.post("/api/logs/analyze", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert r.status_code == 422 and "missing required channels" in r.json()["detail"]


def test_predict_and_domain_validation(client):
    r = client.post("/api/predict", json={"rpm": 5000, "boost_bar": 1.5, "lam": 0.85, "spark_deg": 15})
    assert r.status_code == 200
    body = r.json()
    assert body["surrogate"]["torque_nm"] > 0 and body["surrogate"]["torque_sigma"] >= 0
    assert body["physics"]["torque_nm"] > 0
    assert len(body["sweep"]["spark_deg"]) == len(body["sweep"]["torque_mean"]) == len(body["sweep"]["physics_torque"])
    # outside the surrogate's training domain -> rejected, not extrapolated
    assert client.post("/api/predict", json={"rpm": 9000}).status_code == 422


def test_optimize_job_streams_progress_then_result(client):
    r = client.post("/api/optimize", json={"rpm_start": 4000, "rpm_end": 5600, "rpm_step": 800})
    assert r.status_code == 202
    job_id = r.json()["id"]

    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as s:
        name = None
        for line in s.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line[5:])))
                if name in ("done", "error"):
                    break
    assert events[-1][0] == "done", events[-1]
    result = events[-1][1]["result"]
    assert [row["rpm"] for row in result["rows"]] == [4000, 4800, 5600]
    assert len(result["baseline_power_hp"]) == 3
    assert any(name == "progress" for name, _ in events)

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done" and status["result"]["gain_hp"] == result["gain_hp"]
    assert client.get("/api/jobs/doesnotexist").status_code == 404


def test_telemetry_ws_frames_decode_and_faults_are_detectable(client):
    dbc = client.get("/api/telemetry/dbc").json()
    assert {f["frame_id"] for f in dbc["frames"]} == set(FRAMES_BY_ID)

    with client.websocket_connect("/api/telemetry/ws") as ws:
        msg = ws.receive_json()
        for fr in msg["frames"]:
            data = bytes.fromhex(fr["data"])
            assert crc_ok(fr["id"], data)
            assert "counter" in decode(FRAMES_BY_ID[fr["id"]], data)

        ws.send_json({"cmd": "corrupt"})
        bad = 0
        for _ in range(10):
            bad += sum(not crc_ok(f["id"], bytes.fromhex(f["data"])) for f in ws.receive_json()["frames"])
        assert bad == 1


def test_rate_limit_returns_429(ensemble):
    settings = Settings()
    settings.limits = {**settings.limits, "predict": (0.001, 2)}
    with TestClient(create_app(settings, ensemble=ensemble)) as c:
        codes = [c.post("/api/predict", json={}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
