// Chart containers: a titled card and an HTML legend (axes/tooltip live in axes.tsx).
import type { ReactNode } from 'react'

export function Legend(props: { items: { label: string; color: string; kind?: 'line' | 'band' | 'dash' }[] }) {
  return (
    <div className="legend">
      {props.items.map((it) => (
        <span key={it.label} style={{ color: it.color }}>
          <i className={it.kind === 'band' ? 'band' : it.kind === 'dash' ? 'dash' : ''} style={{ background: it.color }} />
          <span style={{ color: 'var(--ink-2)' }}>{it.label}</span>
        </span>
      ))}
    </div>
  )
}

export function ChartCard(props: { title: string; sub?: string; legend?: ReactNode; children: ReactNode; short?: boolean }) {
  return (
    <div className="card">
      <h3>{props.title}</h3>
      {props.sub && <p className="sub">{props.sub}</p>}
      {props.legend}
      <div className={props.short ? 'chart short' : 'chart'}>{props.children}</div>
    </div>
  )
}
