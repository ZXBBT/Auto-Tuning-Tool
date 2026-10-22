// Browser-side CAN decoder: mirrors dynamis.telemetry.can (Intel byte order, CRC-8
// SAE J1850 over data-ID + payload[1..7], 4-bit alive counter). The frame layout comes
// from /api/telemetry/dbc, so nothing about the signals is hard-coded here.
import type { FrameDef, SignalDef } from './api'

export function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2)
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16)
  return out
}

export function crc8J1850(data: Uint8Array): number {
  let crc = 0xff
  for (const b of data) {
    crc ^= b
    for (let i = 0; i < 8; i++) crc = crc & 0x80 ? ((crc << 1) ^ 0x1d) & 0xff : (crc << 1) & 0xff
  }
  return crc ^ 0xff
}

export function crcOk(frameId: number, payload: Uint8Array): boolean {
  const buf = new Uint8Array(9)
  buf[0] = frameId & 0xff
  buf[1] = (frameId >> 8) & 0xff
  buf.set(payload.subarray(1, 8), 2)
  return payload[0] === crc8J1850(buf)
}

// 64-bit payload as a BigInt (little-endian), so bit fields can straddle byte borders
function payloadWord(payload: Uint8Array): bigint {
  let w = 0n
  for (let i = payload.length - 1; i >= 0; i--) w = (w << 8n) | BigInt(payload[i])
  return w
}

export function decodeSignal(sig: SignalDef, word: bigint): number {
  let raw = Number((word >> BigInt(sig.start_bit)) & ((1n << BigInt(sig.length)) - 1n))
  if (sig.signed && raw >= 2 ** (sig.length - 1)) raw -= 2 ** sig.length
  return raw * sig.scale + sig.offset
}

export function decodeFrame(def: FrameDef, payload: Uint8Array): Record<string, number> {
  const word = payloadWord(payload)
  const out: Record<string, number> = {}
  for (const s of def.signals) out[s.name] = decodeSignal(s, word)
  return out
}
