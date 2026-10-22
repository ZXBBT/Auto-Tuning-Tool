import { useEffect, useState } from 'react'
import { api, type Health, type Meta } from './api'
import About from './pages/About'
import Explorer from './pages/Explorer'
import LiveCan from './pages/LiveCan'
import LogAnalysis from './pages/LogAnalysis'
import Optimizer from './pages/Optimizer'

const TABS = [
  { id: 'logs', label: 'Log analysis' },
  { id: 'optimizer', label: 'Optimizer' },
  { id: 'explorer', label: 'Physics explorer' },
  { id: 'can', label: 'Live CAN' },
  { id: 'about', label: 'How it works' },
] as const
type TabId = (typeof TABS)[number]['id']

function tabFromHash(): TabId {
  const h = location.hash.slice(1)
  return (TABS.find((t) => t.id === h)?.id ?? 'logs') as TabId
}

function readTheme(): string | null {
  try { return localStorage.getItem('theme') } catch { return null }
}

export default function App() {
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [online, setOnline] = useState<boolean | null>(null)
  const [theme, setTheme] = useState<string | null>(readTheme)

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    api.meta().then(setMeta, () => setMeta(null))
    const poll = () => api.health().then((h) => { setHealth(h); setOnline(true) }, () => setOnline(false))
    poll()
    const t = setInterval(poll, 15000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme
    else delete document.documentElement.dataset.theme
  }, [theme])

  const toggleTheme = () => {
    const dark = theme ? theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
    const next = dark ? 'light' : 'dark'
    setTheme(next)
    try { localStorage.setItem('theme', next) } catch { /* storage unavailable: theme lasts this visit */ }
  }

  const go = (id: TabId) => { history.replaceState(null, '', `#${id}`); setTab(id) }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <img className="brand-mark" src="/favicon.svg" alt="" />
          <div>
            <h1>Dynamis</h1>
            <p>Physics-informed ECU calibration · {meta?.engine.name ?? 'EA888 Gen3 2.0T'}</p>
          </div>
        </div>
        <span className="status-pill" title={health ? `API v${health.version}` : undefined}>
          <span className={online ? 'dot ok' : online === false ? 'dot bad' : 'dot'} />
          {online ? `API online · ${meta?.model.members ?? '?'}-model ensemble` : online === false ? 'API unreachable' : 'connecting…'}
        </span>
        <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle light/dark theme" title="Toggle theme">◐</button>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => go(t.id)}>{t.label}</button>
        ))}
      </nav>

      <div className="caveat" role="note">
        <strong>⚠ Simulated</strong>
        <span>
          {meta?.caveat ?? 'All model outputs come from an uncalibrated physics simulator. They demonstrate the method, not a real-world tune.'}
        </span>
      </div>

      <main>
        {tab === 'logs' && <LogAnalysis />}
        {tab === 'optimizer' && <Optimizer meta={meta} />}
        {tab === 'explorer' && <Explorer meta={meta} />}
        {tab === 'can' && <LiveCan />}
        {tab === 'about' && <About meta={meta} health={health} />}
      </main>
    </div>
  )
}
