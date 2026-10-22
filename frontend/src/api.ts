// Typed client for the Dynamis HTTP API (same origin: /api/*).

export type Range = [number, number]

export interface Meta {
  engine: { name: string; cylinders: number; displacement_l: number; compression_ratio: number }
  model: { members: number | null; features: string[]; targets: string[] }
  domain: Record<'rpm' | 'boost_bar' | 'charge_temp_c' | 'lambda' | 'octane' | 'spark_deg', Range>
  default_limits: Record<string, number>
  caveat: string
}

export interface Health { status: string; version: string; model_loaded: boolean; uptime_s: number }

export interface Sample { id: string; title: string; detail: string }

export interface Finding {
  category: 'knock' | 'fueling' | 'boost' | 'timing' | 'general'
  severity: 'info' | 'low' | 'medium' | 'high'
  message: string
  rpm_range: Range | null
  source: 'observed' | 'model-estimated'
}

export interface Analysis {
  source: string
  qa: { rows: number; duration_s: number; sample_rate_hz: number | null; channels_present: string[]; wot_segments: number }
  wot: { t_start: number; t_end: number } | null
  wot_rpm: Range | null
  findings: Finding[]
  est_power_left_hp: number
  report_text: string
  series: Record<string, (number | null)[]>
  caveat: string
}

export interface PredictIn {
  rpm: number; boost_bar: number; lam: number; spark_deg: number; charge_temp_c: number; octane: number
}

export interface Prediction {
  surrogate: { torque_nm: number; torque_sigma: number; power_hp: number; knock_margin: number; knock_margin_sigma: number }
  physics: { torque_nm: number; power_hp: number; knock_margin: number; mbt_deg: number; knock_limited_deg: number; egt_c: number; afr: number }
  sweep: {
    spark_deg: number[]; torque_mean: number[]; torque_sigma: number[]
    knock_margin_mean: number[]; knock_margin_sigma: number[]
    physics_torque: number[]; physics_knock_margin: number[]
  }
}

export interface OptimizeIn {
  octane: number; charge_temp_c: number; boost_max_bar: number; knock_margin_min: number
  lam_min: number; sigma_k: number; rpm_start: number; rpm_end: number; rpm_step: number
}

export interface TuneRow {
  rpm: number; boost_bar: number; lambda: number; spark_deg: number; torque_nm: number
  power_hp: number; knock_margin: number; sigma_torque: number; active_limit: string
}

export interface TuneResult {
  rows: TuneRow[]
  baseline_power_hp: number[]
  baseline: { spark_deg: number; boost_bar: number; lambda: number }
  peak_power_hp: number
  baseline_peak_hp: number
  gain_hp: number
  limits: Record<string, number>
  params: OptimizeIn
  caveat: string
}

export interface JobSnapshot {
  id: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: { done: number; total: number; info: Record<string, unknown> }
  error: string | null
  started: number | null
  result?: TuneResult | null
}

export interface SignalDef {
  name: string; start_bit: number; length: number; scale: number; offset: number; signed: boolean; unit: string
}
export interface FrameDef { frame_id: number; name: string; period_ms: number; signals: SignalDef[] }

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const postJSON = <T>(url: string, body: unknown, signal?: AbortSignal) =>
  request<T>(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })

export const api = {
  health: () => request<Health>('/api/health'),
  meta: () => request<Meta>('/api/meta'),
  samples: () => request<Sample[]>('/api/samples'),
  sampleAnalysis: (id: string, octane: number) =>
    request<Analysis>(`/api/samples/${encodeURIComponent(id)}/analysis?octane=${octane}`),
  analyzeUpload: (file: File, octane: number) => {
    const form = new FormData()
    form.append('file', file)
    form.append('octane', String(octane))
    return request<Analysis>('/api/logs/analyze', { method: 'POST', body: form })
  },
  predict: (body: PredictIn, signal?: AbortSignal) => postJSON<Prediction>('/api/predict', body, signal),
  optimize: (body: OptimizeIn) => postJSON<JobSnapshot>('/api/optimize', body),
  job: (id: string) => request<JobSnapshot>(`/api/jobs/${id}`),
  dbc: () => request<{ frames: FrameDef[]; note: string }>('/api/telemetry/dbc'),
}

/** Follow a job's Server-Sent Events until it finishes. Returns an unsubscribe function. */
export function followJob(
  id: string,
  onProgress: (s: JobSnapshot) => void,
  onDone: (s: JobSnapshot) => void,
  onError: (msg: string) => void,
): () => void {
  const es = new EventSource(`/api/jobs/${id}/events`)
  es.addEventListener('progress', (e) => onProgress(JSON.parse((e as MessageEvent).data)))
  es.addEventListener('done', (e) => { es.close(); onDone(JSON.parse((e as MessageEvent).data)) })
  es.addEventListener('error', (e) => {
    const data = (e as MessageEvent).data
    es.close()
    // a server-sent "error" event carries the job; a bare one is a dropped connection
    if (data) onError(JSON.parse(data).error ?? 'job failed')
    else api.job(id).then((s) => (s.status === 'done' ? onDone(s) : onError('connection to the server was lost')), () => onError('connection to the server was lost'))
  })
  return () => es.close()
}

export function telemetrySocketUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/api/telemetry/ws`
}
