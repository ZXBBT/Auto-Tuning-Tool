"""In-process background jobs for long-running work (the optimizer).

A request submits a job and gets an id back immediately; a single worker thread runs
jobs one at a time (the model is shared and the work is CPU-bound, so parallelism buys
nothing), and clients follow progress over Server-Sent Events. Finished jobs are kept
for a while so a client can reconnect and still read the result.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


class QueueFull(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"           # queued | running | done | error
    done: int = 0
    total: int = 0
    info: dict = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    version: int = 0                 # bumped on every state change (SSE change detection)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": {"done": self.done, "total": self.total, "info": self.info},
            "error": self.error,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
        }


class JobManager:
    def __init__(self, max_pending: int = 8, keep: int = 64, initializer: Callable[[], None] | None = None):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dynamis-job", initializer=initializer)
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self.max_pending = max_pending
        self.keep = keep

    def submit(self, kind: str, fn: Callable[[Callable], Any]) -> Job:
        """Queue ``fn(progress)``; ``progress(done, total, info)`` updates the job."""
        with self._lock:
            pending = sum(j.status in ("queued", "running") for j in self._jobs.values())
            if pending >= self.max_pending:
                raise QueueFull(f"{pending} jobs already pending")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind)
            self._jobs[job.id] = job
            self._evict()
        self._pool.submit(self._run, job, fn)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _run(self, job: Job, fn: Callable[[Callable], Any]) -> None:
        def progress(done: int, total: int, info: dict | None = None) -> None:
            job.done, job.total, job.info = done, total, info or {}
            job.version += 1

        job.status, job.started = "running", time.time()
        job.version += 1
        try:
            job.result = fn(progress)
            job.status = "done"
        except Exception as e:  # report any failure to the client instead of dying silently
            job.status, job.error = "error", f"{type(e).__name__}: {e}"
        job.finished = time.time()
        job.version += 1

    def _evict(self) -> None:
        finished = [k for k, j in self._jobs.items() if j.status in ("done", "error")]
        for k in finished[: max(0, len(self._jobs) - self.keep)]:
            del self._jobs[k]

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
