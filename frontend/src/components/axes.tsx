// Shared chart chrome: recessive axes/grid and a styled crosshair tooltip.
// Recharts finds its axes/grid/tooltip by element type among a chart's direct children,
// so these are plain functions returning Recharts elements, not wrapper components.
import { CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipProps } from 'recharts'
import { C } from './theme'

export function grid() {
  return <CartesianGrid stroke={C.grid} vertical={false} />
}

export function xAxis(props: { dataKey: string; unit?: string; domain?: [number | string, number | string]; ticks?: number[]; fmt?: (v: number) => string }) {
  return (
    <XAxis
      dataKey={props.dataKey}
      type="number"
      domain={props.domain ?? ['dataMin', 'dataMax']}
      ticks={props.ticks}
      tickFormatter={props.fmt}
      unit={props.unit}
      stroke={C.axis}
      tickLine={false}
      tickMargin={6}
      allowDecimals={false}
    />
  )
}

export function yAxis(props: { unit?: string; ticks?: number[]; domain?: [number | string | ((v: number) => number), number | string | ((v: number) => number)]; width?: number; fmt?: (v: number) => string }) {
  return (
    <YAxis
      unit={props.unit}
      domain={props.domain ?? ['auto', 'auto']}
      width={props.width ?? 48}
      ticks={props.ticks}
      tickFormatter={props.fmt}
      axisLine={false}
      tickLine={false}
      tickMargin={4}
    />
  )
}

export interface SeriesSpec { key: string; label: string; color: string; unit?: string; digits?: number }

/** Crosshair tooltip listing the given series at the hovered x. */
export function tip(props: { series: SeriesSpec[]; xLabel: (x: number) => string }) {
  return (
    <Tooltip
      cursor={{ stroke: C.axis, strokeWidth: 1 }}
      isAnimationActive={false}
      content={(p: TooltipProps<number, string>) => {
        if (!p.active || !p.payload?.length) return null
        const row = p.payload[0].payload as Record<string, number | null>
        return (
          <div className="tooltip">
            <div className="t-head">{props.xLabel(Number(p.label))}</div>
            {props.series.map((s) => {
              const v = row[s.key]
              if (v === undefined || v === null) return null
              return (
                <div className="t-row" key={s.key}>
                  <i style={{ background: s.color }} />
                  {s.label}
                  <b>{v.toFixed(s.digits ?? 1)}{s.unit ? ` ${s.unit}` : ''}</b>
                </div>
              )
            })}
          </div>
        )
      }}
    />
  )
}
