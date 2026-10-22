"""Tests for the CAN codec + simulated telemetry stream (torch-free)."""

from __future__ import annotations

import pytest

from dynamis.telemetry import FRAMES_BY_ID, build_cycle, crc8_j1850, crc_ok, decode, encode, frames
from dynamis.telemetry.can import FrameDef, Signal


def test_crc8_j1850_check_value():
    assert crc8_j1850(b"123456789") == 0x4B  # published check value for CRC-8/SAE-J1850


def test_round_trip_within_resolution():
    f = FRAMES_BY_ID[0x100]
    vals = {"rpm": 6123.4, "torque_nm": -42.7, "pedal_pct": 87.0, "gear": 3}
    out = decode(f, encode(f, vals, counter=9))
    assert out["rpm"] == pytest.approx(6123.4, abs=0.25)
    assert out["torque_nm"] == pytest.approx(-42.7, abs=0.1)  # signed, two's complement
    assert out["pedal_pct"] == pytest.approx(87.0, abs=0.4)
    assert out["gear"] == 3
    assert out["counter"] == 9


def test_counter_wraps_and_values_saturate():
    f = FrameDef(0x1, "T", 10, (Signal("crc", 0, 8), Signal("counter", 8, 4), Signal("x", 16, 8, 1.0, 0.0, True)))
    out = decode(f, encode(f, {"x": 500}, counter=17))
    assert out["counter"] == 1        # 4-bit counter wraps
    assert out["x"] == 127            # saturates at the signed 8-bit max instead of wrapping
    assert decode(f, encode(f, {"x": -500}, counter=0))["x"] == -128


def test_crc_detects_single_bit_flips():
    f = FRAMES_BY_ID[0x101]
    payload = encode(f, {"map_kpa": 231.0, "charge_temp_c": 45, "lambda": 0.85}, counter=3)
    assert crc_ok(f.frame_id, payload)
    for byte in range(1, 8):
        for bit in range(8):
            bad = bytearray(payload)
            bad[byte] ^= 1 << bit
            assert not crc_ok(f.frame_id, bytes(bad))
    # the frame id is part of the CRC: the same payload on another id is rejected
    assert not crc_ok(0x102, payload)


def test_stream_is_valid_and_contains_a_wot_pull():
    cyc = build_cycle()
    assert max(cyc["rpm"]) > 6500 and max(cyc["pedal_pct"]) == 100
    it = frames(cyc)
    for tick in range(40):
        batch = next(it)
        assert [fr.frame_id for fr in batch] == [0x100, 0x101, 0x102]
        for fr in batch:
            assert len(fr.data) == 8 and crc_ok(fr.frame_id, fr.data)
            assert decode(FRAMES_BY_ID[fr.frame_id], fr.data)["counter"] == tick % 16
