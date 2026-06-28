"""Terminal 'pulse' — a throttled one-line progress heartbeat for long jobs.

Lives in the CLI layer so the library (model/optimize/data) stays UI-free: those take a
plain ``progress(done, total, info)`` callback, and this renders it. On a TTY it draws a
carriage-return bar with a live ETA; when piped/redirected it falls back to one line per
~10% so logs stay readable.
"""

from __future__ import annotations

import sys
import time
from typing import Any, TextIO


def _fmt(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _hms(seconds: float) -> str:
    s = int(max(0.0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:d}:{sec:02d}"


class Pulse:
    """A callable progress reporter: ``pulse(done, total, info)``.

    Throttled to ``min_interval`` seconds on a TTY (so it never floods the terminal),
    and to decile steps when output is not a TTY.
    """

    def __init__(self, label: str, *, min_interval: float = 0.1, stream: TextIO | None = None):
        self.label = label
        self.min_interval = min_interval
        self.stream = stream or sys.stderr
        self._tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self._start = time.monotonic()
        self._last_emit = 0.0
        self._last_decile = -1
        self._width = 0

    def __call__(self, done: int, total: int, info: dict | None = None) -> None:
        final = total <= 0 or done >= total
        now = time.monotonic()
        if self._tty:
            if not final and now - self._last_emit < self.min_interval:
                return
        else:
            decile = int(10 * done / total) if total else 10
            if not final and decile <= self._last_decile:
                return
            self._last_decile = decile
        self._last_emit = now

        frac = (done / total) if total else 1.0
        elapsed = now - self._start
        eta = (elapsed / frac - elapsed) if frac > 0 else 0.0
        extra = "  ".join(f"{k}={_fmt(v)}" for k, v in (info or {}).items())
        line = f"{self.label} {self._bar(frac)} {frac * 100:5.1f}%  {done}/{total}  ETA {_hms(eta)}"
        if extra:
            line += f"  {extra}"
        self._write(line, final)

    @staticmethod
    def _bar(frac: float, width: int = 24) -> str:
        fill = int(frac * width)
        return "[" + "#" * fill + "-" * (width - fill) + "]"

    def _write(self, line: str, final: bool) -> None:
        if self._tty:
            pad = " " * max(0, self._width - len(line))
            self._width = len(line)
            self.stream.write("\r" + line + pad + ("\n" if final else ""))
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
