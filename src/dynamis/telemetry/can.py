"""Minimal DBC-style CAN signal codec (classic CAN, 8-byte payloads, Intel byte order).

A signal is a bit-field inside a frame's 64-bit payload: ``raw`` is an unsigned (or
two's-complement) integer of ``length`` bits starting at ``start_bit`` (LSB-first,
Intel/little-endian numbering), and ``physical = raw * scale + offset``.

Every frame also carries an AUTOSAR-E2E-style protection header: byte 0 is a CRC-8
(SAE J1850) over a data ID + payload bytes 1..7, and the low nibble of byte 1 is a 4-bit
alive counter. A receiver can thus detect corrupted, stale, or dropped frames.

The frame layout below is *illustrative* (made up for this demo), not VAG's real
powertrain CAN matrix.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Signal:
    name: str
    start_bit: int        # LSB position in the 64-bit payload (Intel numbering)
    length: int           # bits
    scale: float = 1.0
    offset: float = 0.0
    signed: bool = False
    unit: str = ""

    @property
    def raw_min(self) -> int:
        return -(1 << (self.length - 1)) if self.signed else 0

    @property
    def raw_max(self) -> int:
        return (1 << (self.length - 1)) - 1 if self.signed else (1 << self.length) - 1


@dataclass(frozen=True)
class FrameDef:
    frame_id: int
    name: str
    period_ms: int
    signals: tuple[Signal, ...]


CRC_SIGNAL = Signal("crc", 0, 8)
COUNTER_SIGNAL = Signal("counter", 8, 4)

EA888_FRAMES: tuple[FrameDef, ...] = (
    FrameDef(0x100, "ENGINE_1", 50, (
        CRC_SIGNAL, COUNTER_SIGNAL,
        Signal("rpm", 16, 16, 0.25, 0.0, False, "rpm"),
        Signal("torque_nm", 32, 16, 0.1, 0.0, True, "Nm"),
        Signal("pedal_pct", 48, 8, 0.4, 0.0, False, "%"),
        Signal("gear", 56, 4, 1.0, 0.0, False, ""),
    )),
    FrameDef(0x101, "AIRPATH", 50, (
        CRC_SIGNAL, COUNTER_SIGNAL,
        Signal("map_kpa", 16, 16, 0.1, 0.0, False, "kPa"),
        Signal("charge_temp_c", 32, 8, 1.0, -40.0, False, "degC"),
        Signal("lambda", 40, 16, 0.001, 0.0, False, ""),
    )),
    FrameDef(0x102, "IGNITION", 50, (
        CRC_SIGNAL, COUNTER_SIGNAL,
        Signal("ignition_deg", 16, 16, 0.1, 0.0, True, "degBTDC"),
        Signal("knock_retard_cyl1", 32, 8, 0.1, 0.0, False, "deg"),
        Signal("knock_retard_cyl2", 40, 8, 0.1, 0.0, False, "deg"),
        Signal("knock_retard_cyl3", 48, 8, 0.1, 0.0, False, "deg"),
        Signal("knock_retard_cyl4", 56, 8, 0.1, 0.0, False, "deg"),
    )),
)
FRAMES_BY_ID = {f.frame_id: f for f in EA888_FRAMES}


def crc8_j1850(data: bytes) -> int:
    """CRC-8 SAE J1850: poly 0x1D, init 0xFF, final XOR 0xFF (as used by AUTOSAR E2E P1)."""
    crc = 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0xFF


def frame_crc(frame_id: int, payload: bytes) -> int:
    """E2E CRC over the 16-bit data ID (= frame ID, little-endian) + payload bytes 1..7."""
    return crc8_j1850(frame_id.to_bytes(2, "little") + bytes(payload[1:8]))


def _to_raw(sig: Signal, value: float) -> int:
    raw = round((value - sig.offset) / sig.scale)
    raw = max(sig.raw_min, min(sig.raw_max, raw))  # saturate rather than wrap
    return raw & ((1 << sig.length) - 1)           # two's complement for signed


def _from_raw(sig: Signal, raw: int) -> float:
    if sig.signed and raw & (1 << (sig.length - 1)):
        raw -= 1 << sig.length
    return raw * sig.scale + sig.offset


def encode(frame: FrameDef, values: dict[str, float], counter: int) -> bytes:
    """Pack physical values into an 8-byte payload, then fill in counter and CRC."""
    word = 0
    for sig in frame.signals:
        if sig.name == "crc":
            continue
        v = counter & 0xF if sig.name == "counter" else values.get(sig.name, sig.offset)
        word |= _to_raw(sig, v) << sig.start_bit
    payload = bytearray(word.to_bytes(8, "little"))
    payload[0] = frame_crc(frame.frame_id, payload)
    return bytes(payload)


def decode(frame: FrameDef, payload: bytes) -> dict[str, float]:
    """Unpack all signals (including crc/counter) to physical values."""
    word = int.from_bytes(payload, "little")
    return {
        sig.name: _from_raw(sig, (word >> sig.start_bit) & ((1 << sig.length) - 1))
        for sig in frame.signals
    }


def crc_ok(frame_id: int, payload: bytes) -> bool:
    return payload[0] == frame_crc(frame_id, payload)


def dbc_json() -> list[dict]:
    """The frame/signal table as plain dicts (served to the browser-side decoder)."""
    return [
        {
            "frame_id": f.frame_id,
            "name": f.name,
            "period_ms": f.period_ms,
            "signals": [asdict(s) for s in f.signals],
        }
        for f in EA888_FRAMES
    ]
