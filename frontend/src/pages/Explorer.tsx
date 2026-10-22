import { useEffect, useMemo, useState } from 'react'
import { Area, ComposedChart, Line, ReferenceLine, ResponsiveContainer } from 'recharts'
import { api, type Meta, type PredictIn, type Prediction } from '../api'
import { grid, tip, xAxis, yAxis } from '../components/axes'
import { ChartCard, Legend } from '../components/charts'
import { C, margin } from '../components/theme'
import { ErrorBox, PageIntro, Slider, Tile } from '../components/ui'

const INITIAL: PredictIn = { rpm: 5000, boost_bar: 1.5, lam: 0.85, spark_deg: 15, charge_temp_c: 45, octane: 98 }

export default function Explorer({ meta }: { meta: Meta | null }) {
  const [p, setP] = useState<PredictIn>(INITIAL)
  const [pred, setPred] = useState<Prediction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof PredictIn) => (v: number) => setP((prev) => ({ ...prev, [k]: v }))

  // debounce slider drags, and cancel superseded requests so responses can't arrive out of order
  useEffect(() => {
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      api.predict(p, ctrl.signal).then(
        (r) => { setPred(r); setError(null) },
        (e) => { if (e.name !== 'AbortError') setError(e.message) },
      )
    }, 120)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [p])

  const rows = useMemo(() => {
    if (!pred) return []
    const s = pred.sweep
    return s.spark_deg.map((x, i) => ({
      spark: x,
      tq: s.torque_mean[i],
      tq_band: [s.torque_mean[i] - 2 * s.torque_sigma[i], s.torque_mean[i] + 2 * s.torque_sigma[i]],
      tq_phys: s.physics_torque[i],
      km: s.knock_margin_mean[i],
      km_band: [s.knock_margin_mean[i] - 2 * s.knock_margin_sigma[i], s.knock_margin_mean[i] + 2 * s.knock_margin_sigma[i]],
      km_phys: s.physics_knock_margin[i],
    }))
  }, [pred])

  const d = meta?.domain
  const sg = pred?.surrogate
  const ph = pred?.physics
  const knocking = ph && p.spark_deg > ph.knock_limited_deg
  const sparkLabel = (x: number) => `spark ${x.toFixed(1)}°`

  return (
    <>
      <PageIntro title="Physics explorer">
        Pick an operating point and a calibration. The neural surrogate (an ensemble of {meta?.model.members ?? 5} networks) predicts torque and
        knock margin with an uncertainty band, next to the physics model it was trained to imitate. Advance the spark
        past the knock limit and watch the margin hit zero.
      </PageIntro>

      <div className="grid-side">
        <div className="card">
          <h3>Operating point</h3>
          <p className="sub">Ranges are limited to the surrogate's training domain.</p>
          <Slider label="Engine speed" value={p.rpm} min={d?.rpm[0] ?? 2500} max={d?.rpm[1] ?? 7000} step={100} onChange={set('rpm')} fmt={(v) => `${v} rpm`} />
          <Slider label="Boost" value={p.boost_bar} min={d?.boost_bar[0] ?? 0.3} max={d?.boost_bar[1] ?? 2} step={0.05} onChange={set('boost_bar')} fmt={(v) => `${v.toFixed(2)} bar`} />
          <Slider label="Lambda" value={p.lam} min={d?.lambda[0] ?? 0.78} max={d?.lambda[1] ?? 1} step={0.01} onChange={set('lam')} fmt={(v) => v.toFixed(2)} />
          <Slider label="Spark advance" value={p.spark_deg} min={d?.spark_deg[0] ?? 5} max={d?.spark_deg[1] ?? 26} step={0.5} onChange={set('spark_deg')} fmt={(v) => `${v.toFixed(1)}° BTDC`} />
          <Slider label="Charge-air temperature" value={p.charge_temp_c} min={d?.charge_temp_c[0] ?? 30} max={d?.charge_temp_c[1] ?? 70} step={1} onChange={set('charge_temp_c')} fmt={(v) => `${v} °C`} />
          <Slider label="Fuel octane (RON)" value={p.octane} min={d?.octane[0] ?? 91} max={d?.octane[1] ?? 104} step={1} onChange={set('octane')} />
          <button className="btn block" onClick={() => setP(INITIAL)}>Reset</button>
        </div>

        <div className="stack">
          <ErrorBox message={error} />
          {sg && ph && (
            <div className="tiles">
              <Tile label="Torque (surrogate)" value={sg.torque_nm.toFixed(0)} unit="Nm" note={`± ${(2 * sg.torque_sigma).toFixed(1)} (2σ) · physics ${ph.torque_nm.toFixed(0)}`} />
              <Tile label="Power" value={sg.power_hp.toFixed(0)} unit="hp" note={`physics ${ph.power_hp.toFixed(0)} hp`} />
              <Tile label="Knock margin" value={sg.knock_margin.toFixed(3)}
                    note={knocking ? <span style={{ color: 'var(--critical)' }}>⚠ past the knock limit</span> : `physics ${ph.knock_margin.toFixed(3)}`} />
              <Tile label="Knock-limited spark" value={ph.knock_limited_deg.toFixed(1)} unit="°" note={`MBT ${ph.mbt_deg.toFixed(1)}°`} />
            </div>
          )}

          <ChartCard
            title="Torque vs spark advance"
            sub="More advance means more torque, up to MBT (best torque). Past the knock limit, the engine knocks."
            legend={<Legend items={[
              { label: 'Surrogate mean', color: C.s1 },
              { label: '±2σ ensemble band', color: C.s1, kind: 'band' },
              { label: 'Physics model', color: C.s2, kind: 'dash' },
            ]} />}
          >
            <ResponsiveContainer>
              <ComposedChart data={rows} margin={margin}>
                {grid()}
                {xAxis({ dataKey: 'spark', unit: '°', ticks: [5, 10, 15, 20, 25] })}
                {yAxis({ unit: ' Nm', width: 62 })}
                {tip({ xLabel: sparkLabel, series: [
                  { key: 'tq', label: 'Surrogate', color: C.s1, unit: 'Nm', digits: 0 },
                  { key: 'tq_phys', label: 'Physics', color: C.s2, unit: 'Nm', digits: 0 },
                ] })}
                <Area dataKey="tq_band" stroke="none" fill={C.s1} fillOpacity={0.18} isAnimationActive={false} />
                {ph && <ReferenceLine x={ph.knock_limited_deg} stroke={C.critical} strokeWidth={1} label={{ value: 'knock limit', position: 'insideTopRight' }} />}
                <ReferenceLine x={p.spark_deg} stroke={C.axis} strokeWidth={1.5} />
                <Line dataKey="tq_phys" stroke={C.s2} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                <Line dataKey="tq" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard
            title="Knock margin vs spark advance"
            sub="1 − Livengood–Wu autoignition integral. At 0, the end-gas autoignites before the flame arrives."
            legend={<Legend items={[
              { label: 'Surrogate mean', color: C.s1 },
              { label: '±2σ ensemble band', color: C.s1, kind: 'band' },
              { label: 'Physics model', color: C.s2, kind: 'dash' },
            ]} />}
          >
            <ResponsiveContainer>
              <ComposedChart data={rows} margin={margin}>
                {grid()}
                {xAxis({ dataKey: 'spark', unit: '°', ticks: [5, 10, 15, 20, 25] })}
                {yAxis({ domain: [0, 'auto'], fmt: (v) => v.toFixed(2) })}
                {tip({ xLabel: sparkLabel, series: [
                  { key: 'km', label: 'Surrogate', color: C.s1, digits: 3 },
                  { key: 'km_phys', label: 'Physics', color: C.s2, digits: 3 },
                ] })}
                <Area dataKey="km_band" stroke="none" fill={C.s1} fillOpacity={0.18} isAnimationActive={false} />
                <ReferenceLine x={p.spark_deg} stroke={C.axis} strokeWidth={1.5} />
                <Line dataKey="km_phys" stroke={C.s2} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                <Line dataKey="km" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </div>
    </>
  )
}
