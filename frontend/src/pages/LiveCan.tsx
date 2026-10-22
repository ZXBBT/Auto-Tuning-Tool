import { useEffect, useRef, useState } from 'react'
import { Line, LineChart, ResponsiveContainer } from 'recharts'
import { api, telemetrySocketUrl, type FrameDef } from '../api'
import { crcOk, decodeFrame, hexToBytes } from '../can'
import { grid, xAxis, yAxis } from '../components/axes'
import { ChartCard } from '../components/charts'
import { C, margin } from '../components/theme'
import { ErrorBox, PageIntro, Tile } from '../components/ui'

const HISTORY = 200   // ticks kept for the strip charts (10 s at 20 Hz)
const DUMP_LINES = 14
const P_ATM_KPA = 101.325

interface Stats { frames: number; crcErrors: number; seqGaps: number; fps: number }
interface DumpLine { t: number; id: number; hex: string; name: string; status: 'ok' | 'crc' | 'gap' }

export default function LiveCan() {
  const [dbc, setDbc] = useState<Map<number, FrameDef> | null>(null)
  const [conn, setConn] = useState<'idle' | 'connecting' | 'open' | 'closed'>('idle')
  const [closeReason, setCloseReason] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [, setFrameNo] = useState(0) // UI refresh tick

  const ws = useRef<WebSocket | null>(null)
  const values = useRef<Record<string, number>>({})
  const history = useRef<{ t: number; rpm: number; boost: number }[]>([])
  const dump = useRef<DumpLine[]>([])
  const stats = useRef<Stats>({ frames: 0, crcErrors: 0, seqGaps: 0, fps: 0 })
  const lastCounter = useRef<Map<number, number>>(new Map())
  const fpsWindow = useRef<number[]>([])

  useEffect(() => {
    api.dbc().then((r) => setDbc(new Map(r.frames.map((f) => [f.frame_id, f]))), (e) => setError(e.message))
    return () => ws.current?.close()
  }, [])

  // re-render at ~10 Hz instead of on every frame
  useEffect(() => {
    if (conn !== 'open') return
    const t = setInterval(() => setFrameNo((n) => n + 1), 100)
    return () => clearInterval(t)
  }, [conn])

  const connect = () => {
    if (!dbc) return
    setError(null)
    setCloseReason(null)
    stats.current = { frames: 0, crcErrors: 0, seqGaps: 0, fps: 0 }
    lastCounter.current = new Map()
    history.current = []
    dump.current = []
    setConn('connecting')
    const sock = new WebSocket(telemetrySocketUrl())
    ws.current = sock
    sock.onopen = () => setConn('open')
    sock.onclose = (e) => {
      setConn('closed')
      if (e.reason) setCloseReason(e.reason)
      else if (e.code !== 1000) setCloseReason(`connection closed (code ${e.code})`)
    }
    sock.onerror = () => setError('WebSocket error: is the API server reachable?')
    sock.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as { t: number; frames: { id: number; data: string }[] }
      const now = performance.now()
      fpsWindow.current.push(now)
      while (fpsWindow.current.length && now - fpsWindow.current[0] > 1000) fpsWindow.current.shift()
      const st = stats.current
      for (const f of msg.frames) {
        const def = dbc.get(f.id)
        if (!def) continue
        const bytes = hexToBytes(f.data)
        st.frames++
        let status: DumpLine['status'] = 'ok'
        if (!crcOk(f.id, bytes)) {
          st.crcErrors++
          status = 'crc' // a corrupted frame's values are untrusted: drop them
          // it still occupied a counter slot; advance so the next good frame isn't also flagged as a gap
          const prev = lastCounter.current.get(f.id)
          if (prev !== undefined) lastCounter.current.set(f.id, (prev + 1) % 16)
        } else {
          const dec = decodeFrame(def, bytes)
          const prev = lastCounter.current.get(f.id)
          if (prev !== undefined && dec.counter !== (prev + 1) % 16) { st.seqGaps++; status = 'gap' }
          lastCounter.current.set(f.id, dec.counter)
          Object.assign(values.current, dec)
        }
        dump.current.push({ t: msg.t, id: f.id, hex: f.data, name: def.name, status })
      }
      if (dump.current.length > DUMP_LINES) dump.current.splice(0, dump.current.length - DUMP_LINES)
      st.fps = fpsWindow.current.length * msg.frames.length
      const v = values.current
      history.current.push({ t: msg.t, rpm: v.rpm ?? 0, boost: (v.map_kpa ?? P_ATM_KPA) - P_ATM_KPA })
      if (history.current.length > HISTORY) history.current.shift()
    }
  }

  const disconnect = () => ws.current?.close(1000)
  const inject = (cmd: 'corrupt' | 'drop') => ws.current?.send(JSON.stringify({ cmd }))

  const v = values.current
  const st = stats.current
  const knock = Math.max(0, ...[1, 2, 3, 4].map((c) => v[`knock_retard_cyl${c}`] ?? 0))
  const open = conn === 'open'
  const fmtT = (t: number) => `${t.toFixed(0)} s`

  return (
    <>
      <PageIntro title="Live CAN telemetry">
        A simulated ECU streams CAN frames over a WebSocket at 20 Hz. The drive cycle loops through idle, a WOT pull,
        lift-off, and cruise. Your browser decodes the raw 8-byte payloads bit by bit, using the frame layout served by
        the API. It checks each frame's CRC-8 and its 4-bit alive counter, the same end-to-end protection automotive ECUs use.
      </PageIntro>

      <div className="stack">
        <ErrorBox message={error} />
        <div className="card">
          <div className="card-head">
            <div className="btn-row">
              {open || conn === 'connecting'
                ? <button className="btn" onClick={disconnect}>Disconnect</button>
                : <button className="btn primary" onClick={connect} disabled={!dbc}>Connect to ECU stream</button>}
              <button className="btn" onClick={() => inject('corrupt')} disabled={!open} title="Flip one random payload bit in the next frame">Inject bit flip</button>
              <button className="btn" onClick={() => inject('drop')} disabled={!open} title="Drop one frame on the server">Drop a frame</button>
            </div>
            <span className="status-pill">
              <span className={open ? 'dot ok' : conn === 'closed' ? 'dot bad' : 'dot'} />
              {open ? `${st.fps} frames/s` : conn === 'connecting' ? 'connecting…' : conn === 'closed' ? 'disconnected' : 'not connected'}
            </span>
          </div>
          {closeReason && <p className="sub" style={{ margin: '8px 0 0' }}>{closeReason}</p>}
        </div>

        <div className="tiles gauges">
          <Gauge label="Engine speed" value={v.rpm} unit="rpm" digits={0} max={7000} />
          <Gauge label="Boost" value={v.map_kpa !== undefined ? (v.map_kpa - P_ATM_KPA) / 100 : undefined} unit="bar" digits={2} max={2} />
          <Gauge label="Torque" value={v.torque_nm} unit="Nm" digits={0} max={450} />
          <Gauge label="Ignition" value={v.ignition_deg} unit="°" digits={1} max={35} />
          <Gauge label="Lambda" value={v.lambda} digits={3} max={1.2} />
          <Gauge label="Knock retard" value={v.rpm !== undefined ? knock : undefined} unit="°" digits={1} max={5} />
          <Gauge label="Pedal" value={v.pedal_pct} unit="%" digits={0} max={100} />
          <Gauge label="Gear" value={v.gear} digits={0} max={6} />
        </div>

        <div className="grid-2">
          <ChartCard title="Engine speed" sub="Last 10 s" short>
            <ResponsiveContainer>
              <LineChart data={[...history.current]} margin={margin}>
                {grid()}
                {xAxis({ dataKey: 't', fmt: fmtT })}
                {yAxis({ domain: [0, 8000], ticks: [0, 2000, 4000, 6000, 8000], width: 52 })}
                <Line dataKey="rpm" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Boost" sub="Gauge kPa, last 10 s" short>
            <ResponsiveContainer>
              <LineChart data={[...history.current]} margin={margin}>
                {grid()}
                {xAxis({ dataKey: 't', fmt: fmtT })}
                {yAxis({ domain: [-100, 200], ticks: [-100, 0, 100, 200] })}
                <Line dataKey="boost" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>

        <div className="grid-2">
          <div className="card">
            <h3>Raw frames</h3>
            <p className="sub">candump-style. CRC failures are dropped before decoding.</p>
            <div className="candump" aria-live="off">
              {dump.current.length === 0 && <span className="dim">no frames yet</span>}
              {dump.current.map((l, i) => (
                <div key={i} className={l.status === 'ok' ? '' : 'bad'}>
                  <span className="dim">({l.t.toFixed(2).padStart(7)})</span>  can0  {l.id.toString(16).toUpperCase().padStart(3, '0')}  [8]  {l.hex.toUpperCase().match(/../g)!.join(' ')}  <span className={l.status === 'ok' ? 'dim' : ''}>{l.status === 'ok' ? l.name : l.status === 'crc' ? 'CRC ERROR' : 'COUNTER GAP'}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3>Link integrity</h3>
            <p className="sub">Detected by the browser-side checks, not reported by the server.</p>
            <div className="tiles">
              <Tile label="Frames received" value={st.frames.toLocaleString()} />
              <Tile label="CRC errors" value={st.crcErrors} note="corrupted payloads" />
              <Tile label="Counter gaps" value={st.seqGaps} note="lost or repeated frames" />
            </div>
            <div className="divider" />
            <p className="sub" style={{ margin: 0 }}>
              Frame layout: {dbc ? [...dbc.values()].map((f) => `0x${f.frame_id.toString(16).toUpperCase()} ${f.name}`).join(' · ') : '…'}.
              Signals are little-endian (Intel) bit fields. Byte 0 is the CRC-8 SAE J1850 over the data ID and bytes 1–7.
              The low nibble of byte 1 is the alive counter. The layout is illustrative, not VW's real CAN matrix.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}

function Gauge(props: { label: string; value: number | undefined; unit?: string; digits: number; max: number }) {
  const v = props.value
  const pct = v === undefined ? 0 : Math.max(0, Math.min(100, (v / props.max) * 100))
  return (
    <div className="tile gauge">
      <div className="label">{props.label}</div>
      <div className="value">
        {v === undefined ? '—' : v.toFixed(props.digits)}
        {props.unit && <small>{props.unit}</small>}
      </div>
      <div className="bar"><div style={{ width: `${pct}%` }} /></div>
    </div>
  )
}
