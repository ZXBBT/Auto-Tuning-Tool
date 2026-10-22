import type { Health, Meta } from '../api'

export default function About({ meta, health }: { meta: Meta | null; health: Health | null }) {
  return (
    <div className="prose">
      <div className="page-intro">
        <h2>How this works</h2>
        <p>
          Dynamis is a physics-informed ECU calibration pipeline for the {meta?.engine.name ?? 'VW EA888 Gen3 2.0T'}.
          This page explains the system behind the demo, from the physics down to the network path your request just took.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Request path</h3>
        <p className="sub">Served from a home PC. Two independent ingress paths reach the same stack.</p>
        <Diagram />
      </div>

      <h3>The model</h3>
      <ul>
        <li><b>Physics core.</b> A 0-D mean-value engine model: speed-density airflow, Wiebe combustion, and a Livengood–Wu
          knock integral with Douaud–Eyzat ignition delay. Heat release is air-limited, so excess fuel only cools the charge.</li>
        <li><b>Neural surrogate.</b> A small MLP trained on simulator data, wrapped as a deep ensemble of {meta?.model.members ?? 5}.
          The spread across members is the uncertainty σ. It's also differentiable, so the optimizer can backpropagate to the calibration inputs.</li>
        <li><b>Constrained optimizer.</b> Adam with sigmoid-reparameterized box limits, plus a linear+quadratic penalty on a
          σ-aware knock-margin floor. It solves the whole RPM sweep as one batch.</li>
        <li><b>Diagnostics.</b> Detectors that keep <i>observed</i> findings (from logged channels) separate from
          <i> model-estimated</i> ones.</li>
      </ul>

      <h3>The web stack</h3>
      <ul>
        <li><b>Backend:</b> FastAPI and uvicorn. Long optimizer runs go to a single worker thread as background jobs, and progress
          streams to the browser over Server-Sent Events. Live telemetry uses a WebSocket. Inputs are validated against the
          model's training domain, and there's per-IP token-bucket rate limiting.
          See the <a href="/api/docs">OpenAPI docs</a>.</li>
        <li><b>Frontend:</b> React, TypeScript, and Vite, with Recharts. The CAN decoder (bit fields, CRC-8, alive counter) runs in the browser.</li>
        <li><b>Deployment:</b> Docker Compose with Caddy (static files, reverse proxy, TLS, security headers) and the API
          container. Ingress is through a Cloudflare Tunnel, or directly through the router with dynamic DNS and Let's Encrypt.</li>
      </ul>

      <h3>Honest limitations</h3>
      <ul>
        <li>The physics parameters are literature priors that haven't been calibrated against real engine logs yet. Every number
          here demonstrates the method; none of it is a real tune.</li>
        <li>The CAN frame layout is illustrative, not the real VW powertrain matrix.</li>
        <li>Recommendations are advisory only. This is for off-road/dyno research, with no emissions-control tampering.</li>
      </ul>

      <footer>
        <span>Dynamis v{health?.version ?? '…'}</span>
        <span>API uptime {health ? `${Math.floor(health.uptime_s / 60)} min` : '…'}</span>
      </footer>
    </div>
  )
}

function Box(props: { x: number; y: number; w: number; h: number; title: string; lines?: string[]; accent?: boolean }) {
  return (
    <g>
      <rect className={props.accent ? 'box accent' : 'box'} x={props.x} y={props.y} width={props.w} height={props.h} rx={8} />
      <text x={props.x + props.w / 2} y={props.y + 22} textAnchor="middle" fontWeight={600}>{props.title}</text>
      {props.lines?.map((l, i) => (
        <text key={l} className="small" x={props.x + props.w / 2} y={props.y + 40 + i * 15} textAnchor="middle">{l}</text>
      ))}
    </g>
  )
}

function Diagram() {
  return (
    <svg className="diagram" viewBox="0 0 900 360" role="img"
         aria-label="Browser reaches Caddy either through Cloudflare's edge and an outbound tunnel, or through the home router's port forward; Caddy serves the frontend and proxies /api to FastAPI.">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="var(--muted)" />
        </marker>
        <marker id="arrow-b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="var(--series-2)" />
        </marker>
      </defs>

      <rect className="group" x={380} y={20} width={505} height={325} rx={12} />
      <text className="small" x={395} y={40}>Home PC · Docker Compose (WSL2)</text>

      <Box x={10} y={150} w={130} h={60} title="Browser" lines={['HTTPS · SSE · WSS']} />
      <Box x={185} y={50} w={160} h={66} title="Cloudflare edge" lines={['DNS · TLS · DDoS shield']} />
      <Box x={185} y={245} w={160} h={66} title="Home router" lines={['NAT · port-forward :443']} />
      <Box x={400} y={50} w={150} h={66} title="cloudflared" lines={['tunnel connector']} />
      <Box x={575} y={150} w={135} h={66} title="Caddy" lines={['reverse proxy · TLS']} accent />
      <Box x={575} y={262} w={135} h={56} title="Static frontend" lines={['React build']} />
      <Box x={735} y={150} w={135} h={66} title="FastAPI" lines={['uvicorn · /api']} accent />
      <Box x={735} y={242} w={135} h={92} title="Pipeline" lines={['physics MVEM', 'surrogate ensemble', 'optimizer jobs']} />

      <path className="edge" d="M140 170 C165 170 160 83 185 83" markerEnd="url(#arrow)" />
      <path className="edge" d="M400 83 L345 83" markerEnd="url(#arrow)" />
      <text className="small" x={372} y={140} textAnchor="middle">outbound tunnel</text>
      <path className="edge" d="M550 83 C570 83 555 170 575 170" markerEnd="url(#arrow)" />
      <path className="edge b" d="M140 190 C165 190 160 278 185 278" markerEnd="url(#arrow-b)" />
      <path className="edge b" d="M345 278 C470 278 520 198 575 198" markerEnd="url(#arrow-b)" />
      <path className="edge" d="M710 183 L735 183" markerEnd="url(#arrow)" />
      <path className="edge" d="M642 216 L642 262" markerEnd="url(#arrow)" />
      <path className="edge" d="M802 216 L802 242" markerEnd="url(#arrow)" />

      <text className="small" x={265} y={30} textAnchor="middle">A · tunnel subdomain</text>
      <text className="small" x={265} y={338} textAnchor="middle" style={{ fill: 'var(--series-2)' }}>B · direct subdomain (DDNS)</text>
    </svg>
  )
}
