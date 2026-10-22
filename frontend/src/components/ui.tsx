import type { ReactNode } from 'react'

export function Tile(props: { label: string; value: ReactNode; unit?: string; note?: ReactNode; hero?: boolean }) {
  return (
    <div className={props.hero ? 'tile hero' : 'tile'}>
      <div className="label">{props.label}</div>
      <div className="value">
        {props.value}
        {props.unit && <small>{props.unit}</small>}
      </div>
      {props.note && <div className="note">{props.note}</div>}
    </div>
  )
}

export function Slider(props: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  fmt?: (v: number) => string
  hint?: string
}) {
  const id = `f-${props.label.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <div className="field">
      <div className="field-row">
        <label htmlFor={id}>{props.label}</label>
        <output htmlFor={id}>{props.fmt ? props.fmt(props.value) : props.value}</output>
      </div>
      <input
        id={id}
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
      {props.hint && <div className="hint">{props.hint}</div>}
    </div>
  )
}

export function PageIntro(props: { title: string; children: ReactNode }) {
  return (
    <div className="page-intro">
      <h2>{props.title}</h2>
      <p>{props.children}</p>
    </div>
  )
}

export function ErrorBox(props: { message: string | null }) {
  return props.message ? <div className="error" role="alert">{props.message}</div> : null
}

const SEV_COLOR: Record<string, string> = {
  info: 'var(--muted)', low: 'var(--warning)', medium: 'var(--serious)', high: 'var(--critical)',
}
const SEV_LABEL: Record<string, string> = { info: 'Info', low: 'Low', medium: 'Medium', high: 'High' }

export function Severity(props: { level: string }) {
  return (
    <span className="sev">
      <i style={{ background: SEV_COLOR[props.level] ?? 'var(--muted)' }} aria-hidden />
      {SEV_LABEL[props.level] ?? props.level}
    </span>
  )
}
