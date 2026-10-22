"""HTTP API for the Dynamis pipeline (FastAPI).

Endpoints (all under /api):
  GET  /health                 liveness + model status
  GET  /meta                   engine, model domain, default safety limits, caveat
  GET  /samples                built-in sample logs
  GET  /samples/{id}/analysis  diagnose a sample log
  POST /logs/analyze           diagnose an uploaded COBB CSV
  POST /predict                surrogate vs physics at one operating point (+ spark sweep)
  POST /optimize               start an optimizer job -> 202 {job}
  GET  /jobs/{id}              job status / result
  GET  /jobs/{id}/events       job progress as Server-Sent Events
  GET  /telemetry/dbc          CAN frame/signal definitions for the live stream
  WS   /telemetry/ws           simulated live ECU CAN stream

Run: ``uvicorn dynamis.api.app:create_app --factory``
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..config import EA888_GEN3
from ..model import data as domain
from ..optimize import SafetyLimits
from ..telemetry import build_cycle, dbc_json, frames
from ..telemetry.stream import TICK_S
from . import service
from .jobs import JobManager, QueueFull
from .ratelimit import TokenBucket, client_ip

log = logging.getLogger("dynamis.api")


@dataclass
class Settings:
    model_path: Path = Path(os.getenv("DYNAMIS_MODEL_PATH", "models/surrogate.pt"))
    device: str = os.getenv("DYNAMIS_DEVICE", "cpu")
    torch_threads: int = int(os.getenv("DYNAMIS_TORCH_THREADS", "2"))
    trust_proxy: bool = os.getenv("DYNAMIS_TRUST_PROXY", "0") == "1"
    max_upload_mb: float = float(os.getenv("DYNAMIS_MAX_UPLOAD_MB", "5"))
    static_dir: str | None = os.getenv("DYNAMIS_STATIC_DIR") or None
    max_ws_clients: int = int(os.getenv("DYNAMIS_MAX_WS", "25"))
    ws_session_s: float = float(os.getenv("DYNAMIS_WS_SESSION_S", "900"))
    # (tokens/s, burst) per client IP
    limits: dict = field(default_factory=lambda: {
        "optimize": (6 / 60, 3), "analyze": (30 / 60, 10), "predict": (10.0, 40), "ws": (6 / 60, 4),
    })


# ------------------------------ request bodies ------------------------------
class PredictIn(BaseModel):
    rpm: float = Field(5000, ge=domain.RPM[0], le=domain.RPM[1])
    boost_bar: float = Field(1.5, ge=domain.BOOST_BAR[0], le=domain.BOOST_BAR[1])
    lam: float = Field(0.85, ge=domain.LAM[0], le=domain.LAM[1])
    spark_deg: float = Field(15.0, ge=domain.SPARK[0], le=domain.SPARK[1])
    charge_temp_c: float = Field(45.0, ge=domain.CHARGE_C[0], le=domain.CHARGE_C[1])
    octane: float = Field(98.0, ge=domain.OCTANE[0], le=domain.OCTANE[1])


_DEFAULT_LIMITS = SafetyLimits()


class OptimizeIn(BaseModel):
    octane: float = Field(98.0, ge=domain.OCTANE[0], le=domain.OCTANE[1])
    charge_temp_c: float = Field(50.0, ge=domain.CHARGE_C[0], le=domain.CHARGE_C[1])
    boost_max_bar: float = Field(_DEFAULT_LIMITS.boost_max_bar, ge=0.5, le=domain.BOOST_BAR[1])
    knock_margin_min: float = Field(_DEFAULT_LIMITS.knock_margin_min, ge=0.0, le=0.5)
    lam_min: float = Field(_DEFAULT_LIMITS.lam_min, ge=domain.LAM[0], le=0.95)
    sigma_k: float = Field(_DEFAULT_LIMITS.sigma_k, ge=0.0, le=3.0)
    rpm_start: int = Field(3000, ge=int(domain.RPM[0]), le=6500)
    rpm_end: int = Field(6800, ge=3000, le=int(domain.RPM[1]))
    rpm_step: int = Field(400, ge=100, le=1000)


# ---------------------------------- model ----------------------------------
def load_or_train(settings: Settings):
    from ..model.data import make_dataset
    from ..model.ensemble import DeepEnsemble

    if settings.model_path.exists():
        log.info("loading surrogate ensemble from %s", settings.model_path)
        return DeepEnsemble.load(str(settings.model_path), device=settings.device)
    log.warning("%s not found; training a quick ensemble (k=3, n=1500)", settings.model_path)
    ens = DeepEnsemble(k=3, device=settings.device).fit(make_dataset(n=1500), epochs=500)
    try:
        settings.model_path.parent.mkdir(parents=True, exist_ok=True)
        ens.save(str(settings.model_path))
    except OSError as e:  # read-only volume is fine; we just retrain next start
        log.warning("could not save trained model: %s", e)
    return ens


def warm_up(ensemble) -> None:
    """Pay torch's one-time lazy-init cost at startup, not on the first user request."""
    service.predict_point(ensemble, **PredictIn().model_dump(), sweep_n=3)
    service.run_optimize(ensemble, {**OptimizeIn().model_dump(), "rpm_start": 4000, "rpm_end": 4000})


# ----------------------------------- app -----------------------------------
def create_app(settings: Settings | None = None, ensemble=None) -> FastAPI:
    settings = settings or Settings()
    buckets = {k: TokenBucket(*v) for k, v in settings.limits.items()}
    state: dict = {"ensemble": ensemble, "started": time.time(), "ws_clients": 0}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import torch

        torch.set_num_threads(settings.torch_threads)
        if state["ensemble"] is None:
            state["ensemble"] = await asyncio.to_thread(load_or_train, settings)
            await asyncio.to_thread(warm_up, state["ensemble"])
        # torch's intra-op thread count is per-thread state: set it on the worker too, or
        # the optimizer runs ~10x slower there from thread oversubscription
        state["jobs"] = JobManager(initializer=lambda: torch.set_num_threads(settings.torch_threads))
        state["cycle"] = await asyncio.to_thread(build_cycle)
        log.info("ready")
        yield
        state["jobs"].shutdown()

    app = FastAPI(title="Dynamis API", version=__version__, lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)

    def limit(kind: str, request: Request) -> None:
        ok, retry = buckets[kind].allow(client_ip(request, settings.trust_proxy))
        if not ok:
            raise HTTPException(429, f"rate limit exceeded for {kind}; retry in {retry:.0f}s",
                                headers={"Retry-After": str(max(1, round(retry)))})

    def ens():
        if state["ensemble"] is None:
            raise HTTPException(503, "model not loaded yet")
        return state["ensemble"]

    @app.exception_handler(service.InputError)
    async def _input_error(_: Request, exc: service.InputError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    # ---------------------------------------------------------------- info
    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "model_loaded": state["ensemble"] is not None,
            "uptime_s": round(time.time() - state["started"], 1),
        }

    @app.get("/api/meta")
    def meta():
        e = state["ensemble"]
        return service.clean({
            "engine": {"name": EA888_GEN3.name, "cylinders": EA888_GEN3.num_cylinders,
                       "displacement_l": EA888_GEN3.displacement_m3 * 1000,
                       "compression_ratio": EA888_GEN3.compression_ratio},
            "model": {"members": e.k if e else None, "features": domain.FEATURES, "targets": domain.TARGETS},
            "domain": service.model_domain(),
            "default_limits": asdict(_DEFAULT_LIMITS),
            "caveat": service.CAVEAT,
        })

    # ---------------------------------------------------------------- logs
    @app.get("/api/samples")
    def samples():
        return [{"id": k, "title": v["title"], "detail": v["detail"]} for k, v in service.SAMPLES.items()]

    @lru_cache(maxsize=16)
    def _sample_analysis(sample_id: str, octane: float) -> dict:
        return service.analyze_log(service.sample_log(sample_id), octane=octane)

    @app.get("/api/samples/{sample_id}/analysis")
    def sample_analysis(sample_id: str, octane: float = 98.0):
        if sample_id not in service.SAMPLES:
            raise HTTPException(404, f"unknown sample {sample_id!r}")
        if not domain.OCTANE[0] <= octane <= domain.OCTANE[1]:
            raise HTTPException(422, f"octane must be within {domain.OCTANE}")
        return _sample_analysis(sample_id, octane)

    @app.post("/api/logs/analyze")
    def analyze_upload(request: Request, file: UploadFile = File(...), octane: float = Form(98.0)):
        limit("analyze", request)
        if not domain.OCTANE[0] <= octane <= domain.OCTANE[1]:
            raise HTTPException(422, f"octane must be within {domain.OCTANE}")
        max_bytes = int(settings.max_upload_mb * 1024 * 1024)
        content = file.file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(413, f"file larger than {settings.max_upload_mb:g} MB")
        lf = service.parse_upload(content, file.filename or "upload.csv")
        return service.analyze_log(lf, octane=octane)

    # ------------------------------------------------------------ explorer
    @app.post("/api/predict")
    def predict(body: PredictIn, request: Request):
        limit("predict", request)
        return service.predict_point(ens(), **body.model_dump())

    # ------------------------------------------------------------ optimizer
    @app.post("/api/optimize", status_code=202)
    def optimize(body: OptimizeIn, request: Request):
        limit("optimize", request)
        if body.rpm_end < body.rpm_start:
            raise HTTPException(422, "rpm_end must be >= rpm_start")
        e, params = ens(), body.model_dump()
        try:
            job = state["jobs"].submit("optimize", lambda progress: service.run_optimize(e, params, progress))
        except QueueFull as exc:
            raise HTTPException(429, f"optimizer busy ({exc}); try again shortly") from exc
        return job.snapshot()

    def _job(job_id: str):
        job = state["jobs"].get(job_id)
        if job is None:
            raise HTTPException(404, "unknown job (it may have expired)")
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job = _job(job_id)
        return {**job.snapshot(), "result": job.result if job.status == "done" else None}

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request):
        job = _job(job_id)

        async def stream():
            seen, last_send = -1, time.monotonic()
            while not await request.is_disconnected():
                if job.version != seen:
                    seen = job.version
                    last_send = time.monotonic()
                    if job.status in ("done", "error"):
                        payload = {**job.snapshot(), "result": job.result}
                        yield f"event: {job.status}\ndata: {json.dumps(payload)}\n\n"
                        return
                    yield f"event: progress\ndata: {json.dumps(job.snapshot())}\n\n"
                elif time.monotonic() - last_send > 15:  # keep idle proxies from closing us
                    last_send = time.monotonic()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------ telemetry
    @app.get("/api/telemetry/dbc")
    def telemetry_dbc():
        return {"frames": dbc_json(), "note": "illustrative frame layout, not the real VAG CAN matrix"}

    @app.websocket("/api/telemetry/ws")
    async def telemetry_ws(ws: WebSocket):
        ok, _ = buckets["ws"].allow(client_ip(ws, settings.trust_proxy))
        if not ok or state["ws_clients"] >= settings.max_ws_clients:
            await ws.close(code=1013, reason="server busy, try again later")
            return
        await ws.accept()
        state["ws_clients"] += 1
        faults: list[str] = []

        async def receive():  # client commands: fault injection to demo the E2E checks
            while True:
                msg = await ws.receive_json()
                if msg.get("cmd") in ("corrupt", "drop") and len(faults) < 10:
                    faults.append(msg["cmd"])

        rx = asyncio.create_task(receive())
        it, t0, tick = frames(state["cycle"]), time.monotonic(), 0
        try:
            while not rx.done() and time.monotonic() - t0 < settings.ws_session_s:
                batch = next(it)
                out = [{"id": f.frame_id, "data": f.data.hex()} for f in batch]
                if faults:
                    k = random.randrange(len(out))
                    if faults.pop(0) == "corrupt":  # flip one payload bit; the CRC will catch it
                        data = bytearray(bytes.fromhex(out[k]["data"]))
                        data[random.randrange(1, 8)] ^= 1 << random.randrange(8)
                        out[k]["data"] = data.hex()
                    else:  # lose a frame; the alive counter will show the gap
                        out.pop(k)
                await ws.send_json({"t": batch[0].t, "frames": out})
                tick += 1
                # schedule against the start time so the stream doesn't drift
                await asyncio.sleep(max(0.0, t0 + tick * TICK_S - time.monotonic()))
            if not rx.done():
                await ws.close(code=1000, reason="session time limit reached")
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            rx.cancel()
            state["ws_clients"] -= 1

    if settings.static_dir:  # single-container mode: serve the built frontend too
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")
    return app
