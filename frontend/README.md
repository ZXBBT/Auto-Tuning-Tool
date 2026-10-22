# Dynamis web app

React + TypeScript + Vite frontend for the Dynamis API. See the repo README's *Web demo* section.

```bash
npm ci
npm run dev     # http://localhost:5173, proxies /api (incl. the WebSocket) to uvicorn on :8000
npm run build   # type-check + production build into dist/ (served by Caddy in Docker)
npm run lint
```

- `src/api.ts` is the typed API client, plus SSE job following and the WebSocket URL.
- `src/can.ts` is the browser-side CAN decoder. It mirrors `dynamis.telemetry.can`.
- `src/pages/` has one component per tab. `src/components/` has the shared UI and chart chrome.
