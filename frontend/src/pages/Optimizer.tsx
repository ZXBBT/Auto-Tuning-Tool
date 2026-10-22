import { useEffect, useMemo, useRef, useState } from 'react'
import { Line, LineChart, ReferenceLine, ResponsiveContainer } from 'recharts'
import { api, followJob, type JobSnapshot, type Meta, type OptimizeIn, type TuneResult } from '../api'
import { grid, tip, xAxis, yAxis } from '../components/axes'
import { ChartCard, Legend } from '../components/charts'
import { C, margin } from '../components/theme'
import { ErrorBox, PageIntro, Slider, Tile } from '../components/ui'
import { downloadCsv } from '../download'

const DEFAULTS: OptimizeIn = {
  octane: 98, charge_temp_c: 50, boost_max_bar: 1.8, knock_margin_min: 0.1, lam_min: 0.78, sigma_k: 1,
  rpm_start: 3000, rpm_end: 6800, rpm_step: 400,
}

const LIMIT_LABEL: Record<string, string> = {
  knock: 'Knock margin', 'boost ceiling': 'Boost ceiling', 'spark authority': 'Spark limit',
  'lambda (rich) limit': 'Rich limit', open: 'None',
}

export default function Optimizer({ meta }: { meta: Meta | null }) {
  const [p, setP] = useState<OptimizeIn>(DEFAULTS)
  const [job, setJob] = useState<JobSnapshot | null>(null)
  const [result, setResult] = useState<TuneResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const startedAt = useRef(0)
  const unsub = useRef<(() => void) | null>(null)
  useEffect(() => () => unsub.current?.(), [])

  const set = (k: keyof OptimizeIn) => (v: number) => setP((prev) => ({ ...prev, [k]: v }))
  const running = job?.status === 'queued' || job?.status === 'running'

  const run = async () => {
    setError(null)
    try {
      const snap = await api.optimize(p)
      setJob(snap)
      startedAt.current = performance.now()
      unsub.current = followJob(
        snap.id,
        setJob,
        (s) => { setJob(s); setResult(s.result ?? null) },
        (msg) => { setJob(null); setError(msg) },
      )
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const frac = job && job.progress.total ? job.progress.done / job.progress.total : 0
  const elapsed = job && running ? (performance.now() - startedAt.current) / 1000 : 0
  const eta = frac > 0.02 ? elapsed / frac - elapsed : null

  const rows = useMemo(
    () => result?.rows.map((r, i) => ({ ...r, baseline_hp: result.baseline_power_hp[i] })) ?? [],
    [result],
  )
  const rpmTicks = rows.length ? thousands(rows[0].rpm, rows[rows.length - 1].rpm) : undefined
  const minMargin = rows.length ? Math.min(...rows.map((r) => r.knock_margin)) : 0
  const rpmLabel = (x: number) => `${x} rpm`
  const d = meta?.domain

  return (
    <>
      <PageIntro title="Calibration optimizer">
        Finds the boost, lambda, and spark advance at each RPM that maximize torque, subject to safety limits. It runs
        gradient descent through the differentiable neural surrogate. The knock-margin floor is made conservative by
        subtracting the ensemble's uncertainty (σ), so the optimizer backs off where the model is unsure.
      </PageIntro>

      <div className="grid-side">
        <div className="card">
          <h3>Limits & conditions</h3>
          <p className="sub">The optimizer may not cross any of these.</p>
          <Slider label="Boost ceiling" value={p.boost_max_bar} min={0.8} max={d?.boost_bar[1] ?? 2} step={0.05}
                  onChange={set('boost_max_bar')} fmt={(v) => `${v.toFixed(2)} bar`} hint="Turbo / hardware limit" />
          <Slider label="Knock-margin floor" value={p.knock_margin_min} min={0} max={0.3} step={0.01}
                  onChange={set('knock_margin_min')} fmt={(v) => v.toFixed(2)} hint="0 = right at the knock limit" />
          <Slider label="Uncertainty penalty" value={p.sigma_k} min={0} max={3} step={0.25}
                  onChange={set('sigma_k')} fmt={(v) => `${v.toFixed(2)} σ`} hint="Margin used = predicted − k·σ" />
          <Slider label="Richest lambda allowed" value={p.lam_min} min={0.78} max={0.9} step={0.01}
                  onChange={set('lam_min')} fmt={(v) => v.toFixed(2)} />
          <Slider label="Fuel octane (RON)" value={p.octane} min={91} max={104} step={1} onChange={set('octane')} />
          <Slider label="Charge-air temperature" value={p.charge_temp_c} min={30} max={70} step={1}
                  onChange={set('charge_temp_c')} fmt={(v) => `${v} °C`} />
          <button className="btn primary block" onClick={run} disabled={running}>
            {running ? 'Optimizing…' : 'Run optimizer'}
          </button>
          <div style={{ marginTop: 8 }}>
            <button className="btn block" onClick={() => setP(DEFAULTS)} disabled={running}>Reset to defaults</button>
          </div>
        </div>

        <div className="stack">
          <ErrorBox message={error} />
          {job && running && (
            <div className="card" aria-live="polite">
              <div className="card-head">
                <h3>{job.status === 'queued' ? 'Queued…' : 'Optimizing'}</h3>
                <span className="mono" style={{ color: 'var(--muted)', fontSize: 12 }}>job {job.id}</span>
              </div>
              <p className="sub">Progress streamed live from the server (Server-Sent Events).</p>
              <div className="progress"><div style={{ width: `${(frac * 100).toFixed(1)}%` }} /></div>
              <div className="progress-meta">
                <span>step {job.progress.done} / {job.progress.total || '…'}</span>
                <span>{eta !== null ? `~${eta.toFixed(1)} s left` : ''}</span>
              </div>
            </div>
          )}

          {!result && !running && (
            <div className="card empty">Set the limits and press <b>Run optimizer</b>.</div>
          )}

          {result && (
            <>
              <div className="tiles">
                <Tile hero label="Optimized peak power" value={Math.round(result.peak_power_hp)} unit="hp" />
                <Tile hero label="Baseline peak power" value={Math.round(result.baseline_peak_hp)} unit="hp"
                      note={`${result.baseline.spark_deg}° · ${result.baseline.boost_bar} bar · λ ${result.baseline.lambda}`} />
                <Tile hero label="Gain" value={<span className="delta-up">+{Math.round(result.gain_hp)}</span>} unit="hp" />
                <Tile hero label="Worst knock margin" value={minMargin.toFixed(3)} note={`floor ${result.limits.knock_margin_min}`} />
              </div>

              <ChartCard
                title="Power vs RPM"
                sub="Surrogate prediction (simulated engine)"
                legend={<Legend items={[{ label: 'Optimized', color: C.s1 }, { label: 'Baseline calibration', color: C.muted, kind: 'dash' }]} />}
              >
                <ResponsiveContainer>
                  <LineChart data={rows} margin={margin}>
                    {grid()}
                    {xAxis({ dataKey: 'rpm', ticks: rpmTicks })}
                    {yAxis({ unit: ' hp', width: 60 })}
                    {tip({ xLabel: rpmLabel, series: [
                      { key: 'power_hp', label: 'Optimized', color: C.s1, unit: 'hp', digits: 0 },
                      { key: 'baseline_hp', label: 'Baseline', color: C.muted, unit: 'hp', digits: 0 },
                    ] })}
                    <Line dataKey="baseline_hp" stroke={C.muted} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                    <Line dataKey="power_hp" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, strokeWidth: 0 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>

              <div className="grid-2">
                <ChartCard title="Spark advance" sub="°BTDC. Rises with RPM as knock eases off." short>
                  <ResponsiveContainer>
                    <LineChart data={rows} margin={margin}>
                      {grid()}
                      {xAxis({ dataKey: 'rpm', ticks: rpmTicks })}
                      {yAxis({ unit: '°' })}
                      {tip({ xLabel: rpmLabel, series: [{ key: 'spark_deg', label: 'Spark', color: C.s1, unit: '°' }] })}
                      <Line dataKey="spark_deg" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, strokeWidth: 0 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Knock margin" sub="Must stay above the floor (red line)" short>
                  <ResponsiveContainer>
                    <LineChart data={rows} margin={margin}>
                      {grid()}
                      {xAxis({ dataKey: 'rpm', ticks: rpmTicks })}
                      {yAxis({ domain: [0, 'auto'], fmt: (v) => v.toFixed(2) })}
                      <ReferenceLine y={result.limits.knock_margin_min} stroke={C.critical} strokeWidth={1.5} />
                      {tip({ xLabel: rpmLabel, series: [{ key: 'knock_margin', label: 'Margin', color: C.s1, digits: 3 }] })}
                      <Line dataKey="knock_margin" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, strokeWidth: 0 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Boost" sub="bar gauge" short>
                  <ResponsiveContainer>
                    <LineChart data={rows} margin={margin}>
                      {grid()}
                      {xAxis({ dataKey: 'rpm', ticks: rpmTicks })}
                      {yAxis({ domain: [0, 2], ticks: [0, 0.5, 1, 1.5, 2], fmt: (v) => v.toFixed(1) })}
                      <ReferenceLine y={result.limits.boost_max_bar} stroke={C.axis} strokeWidth={1} />
                      {tip({ xLabel: rpmLabel, series: [{ key: 'boost_bar', label: 'Boost', color: C.s1, unit: 'bar', digits: 2 }] })}
                      <Line dataKey="boost_bar" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, strokeWidth: 0 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
                <ChartCard title="Lambda" sub="Richer (lower) buys knock margin through charge cooling" short>
                  <ResponsiveContainer>
                    <LineChart data={rows} margin={margin}>
                      {grid()}
                      {xAxis({ dataKey: 'rpm', ticks: rpmTicks })}
                      {yAxis({ domain: [0.75, 1.0], ticks: [0.75, 0.8, 0.85, 0.9, 0.95, 1], fmt: (v) => v.toFixed(2) })}
                      {tip({ xLabel: rpmLabel, series: [{ key: 'lambda', label: 'Lambda', color: C.s1, digits: 3 }] })}
                      <Line dataKey="lambda" stroke={C.s1} strokeWidth={2} dot={{ r: 3, fill: C.s1, strokeWidth: 0 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>

              <div className="card">
                <div className="card-head">
                  <div>
                    <h3>Recommended WOT calibration</h3>
                    <p className="sub">"Binding limit" is the constraint that stopped the optimizer at that RPM.</p>
                  </div>
                  <button className="btn" onClick={() => downloadCsv('dynamis-tune.csv', result.rows as unknown as Record<string, unknown>[])}>
                    Download CSV
                  </button>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>RPM</th><th>Boost (bar)</th><th>λ</th><th>Spark (°)</th><th>Torque (Nm)</th>
                        <th>± σ</th><th>Power (hp)</th><th>Knock margin</th><th>Binding limit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((r) => (
                        <tr key={r.rpm}>
                          <td>{r.rpm}</td><td>{r.boost_bar.toFixed(2)}</td><td>{r.lambda.toFixed(3)}</td>
                          <td>{r.spark_deg.toFixed(1)}</td><td>{r.torque_nm.toFixed(0)}</td><td>{r.sigma_torque.toFixed(1)}</td>
                          <td>{r.power_hp.toFixed(0)}</td><td>{r.knock_margin.toFixed(3)}</td>
                          <td>{LIMIT_LABEL[r.active_limit] ?? r.active_limit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}

/** Round-thousand RPM ticks spanning [lo, hi]. */
function thousands(lo: number, hi: number): number[] {
  const out = []
  for (let r = Math.ceil(lo / 1000) * 1000; r <= hi; r += 1000) out.push(r)
  return out
}
