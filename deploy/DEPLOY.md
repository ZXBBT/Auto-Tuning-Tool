# Deploying the Dynamis demo from a home PC

The stack runs in Docker Desktop (WSL2 backend) on a Windows PC. There are two independent
ingress paths into the same containers:

```
                       ┌──────────── home PC · docker compose ─────────────┐
 A  browser ─HTTPS─▶ Cloudflare edge ◀─outbound tunnel─ cloudflared ─┐      │
                       │                                            ▼      │
 B  browser ─HTTPS─▶ router :443 ─NAT/port-forward──────────────▶ Caddy ─/api─▶ FastAPI
                       │                                            │      │
                       │                                   static React app │
                       └───────────────────────────────────────────────────┘
```

| | A: Cloudflare Tunnel | B: direct (port forward) |
|---|---|---|
| Who opens the connection | the PC, **outbound** to Cloudflare | the visitor, **inbound** through the router |
| Router changes | none | port forward 80/443 → PC |
| Works behind CGNAT | yes | no (needs a real public IPv4) |
| Home IP visible | no | yes (it's the A record) |
| TLS terminated at | Cloudflare edge | Caddy on the PC (Let's Encrypt) |
| DNS record | proxied CNAME → `<tunnel-id>.cfargotunnel.com` | grey-cloud A record → home IP, kept current by DDNS |
| Use it for | the live demo (most reliable) | showing the full networking path |

Below, replace `example.com` with your domain. The examples use `tuner.example.com` for
path A and `direct.example.com` for path B.

---

## 0. Local stack (no domain needed)

```bash
# once: train the surrogate the API serves (the models/ folder is mounted read-only)
.venv/bin/dynamis train --out models/surrogate.pt

docker compose up -d --build
# -> http://localhost:8080   (API docs at http://localhost:8080/api/docs)
docker compose ps            # api should be "healthy"
docker compose logs -f api   # follow logs
```

## 1. Domain on Cloudflare

Buy the domain through **Cloudflare Registrar**. The zone then already lives on
Cloudflare's DNS. If you bought it elsewhere, add the site to Cloudflare and change the
registrar's nameservers to the two Cloudflare gives you, then wait for "Active".

## 2. Path A: Cloudflare Tunnel

1. Cloudflare dashboard → **Zero Trust** (first visit: pick a team name and the Free plan) →
   **Networks → Tunnels** → **Create a tunnel** → type **Cloudflared**, name `dynamis`.
2. On the "install connector" step, pick **Docker** and copy only the long token after
   `--token` (it starts with `eyJ`). Don't run the command they show: `compose.yaml` already
   has a pinned `cloudflared` service on the same network as Caddy. Put the token in `.env`,
   and enable the profile so plain `docker compose up -d` starts the connector:
   ```
   TUNNEL_TOKEN=eyJh...
   COMPOSE_PROFILES=tunnel
   ```
3. Start the connector **now**. The wizard won't let you continue until it sees the connector online:
   ```bash
   docker compose up -d
   docker compose logs cloudflared | grep "Registered tunnel connection"   # expect 4, across 2 data centers
   ```
4. **Add route → Published application** (older UI: "Public hostname"). Don't pick private
   network or private hostname. Use subdomain `tuner`, domain `example.com`, empty path,
   service URL **`http://web:8080`**. `web` is Caddy's name on the Compose network, and it's
   plain HTTP because TLS ends at Cloudflare's edge. `https://` here would cause a 502.
   Cloudflare pushes the route to the running connector, so no restart is needed. It also
   creates a **proxied (orange) CNAME** `tuner → <tunnel-id>.cfargotunnel.com`, which must stay orange.
5. Check it:
   ```bash
   docker compose logs cloudflared | grep "Updated to new configuration"
   dig +short tuner.example.com        # Cloudflare anycast IPs, not your home IP
   curl -sI https://tuner.example.com | grep -iE "^(HTTP|server|cf-ray)"
   ```
   Then open it on your phone **on mobile data**, so the test really comes from outside your network.

WebSockets (Live CAN) and Server-Sent Events (optimizer progress) work through the tunnel
without extra settings. Cloudflare injects its Web Analytics beacon into proxied HTML, and
the CSP in `deploy/Caddyfile` allows exactly that script. Visits then show up under
Analytics → Web Analytics.

## 3. Path B: direct through the router

Your router's WAN IP matches what whatismyip.com shows, so you are **not** behind CGNAT
and this path is possible.

1. **Give the PC a fixed LAN IP.** In the router, add a DHCP reservation for the PC's
   Ethernet/Wi-Fi MAC address. In PowerShell, `ipconfig` shows the current IPv4.
2. **Port forward** on the router: TCP 80 → PC:80, TCP 443 → PC:443, and UDP 443 → PC:443
   (the UDP rule is optional and enables HTTP/3). Port 80 is only needed for Let's Encrypt's HTTP
   challenge and the redirect to HTTPS.
3. **Windows firewall.** Docker Desktop publishes container ports on the Windows host. When
   you first allowed Docker Desktop through the firewall, Windows usually created a
   **"Docker Desktop Backend"** rule that allows all its ports. Check for it:
   `Get-NetFirewallRule -DisplayName 'Docker Desktop Backend'`. That same rule is why
   `compose.yaml` binds 8080 to 127.0.0.1: anything Docker publishes on 0.0.0.0 is reachable
   from the LAN. Only if that rule is missing, allow the ports (PowerShell **as Administrator**):
   ```powershell
   New-NetFirewallRule -DisplayName "Dynamis HTTP/HTTPS" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow
   New-NetFirewallRule -DisplayName "Dynamis HTTP/3" -Direction Inbound -Protocol UDP -LocalPort 443 -Action Allow
   ```
4. **DNS + dynamic DNS.** Create a Cloudflare API token (My Profile → API Tokens →
   template "Edit zone DNS", restricted to this zone). Then set up `.env`:
   ```
   DOMAIN_DIRECT=direct.example.com
   ACME_EMAIL=you@example.com
   CF_API_TOKEN=...
   ```
   The `ddns` container creates and updates the `direct` A record with your current public
   IP every 5 minutes, as **DNS only (grey cloud)**. The record must not be proxied, or
   traffic would go through Cloudflare again instead of straight to your router.
   Watch out: a record you add in the dashboard is **proxied by default**. If you created
   one by hand, switch it to DNS only. `dig +short direct.example.com` must print your home
   IP, not Cloudflare's 104.x / 172.67.x addresses.

   Also add `COMPOSE_FILE=compose.yaml:compose.direct.yaml` to `.env`. Plain
   `docker compose ...` commands then include the path B services (`ddns`) without passing
   `-f` twice.
5. Start everything:
   ```bash
   docker compose -f compose.yaml -f compose.direct.yaml --profile tunnel up -d
   docker compose logs web | grep -iE "certificate obtained|error"
   ```
   Caddy obtains a Let's Encrypt certificate for `direct.example.com` on first start and
   renews it automatically. The certificate is stored in the `caddy_data` volume.
   "certificate obtained successfully" also proves the whole inbound path works: Let's
   Encrypt fetched a challenge file from the internet through your router's port 80.
6. Check from **outside** your network (phone on mobile data). Many routers don't support
   hairpin NAT, so `direct.example.com` may not load from inside your own LAN even when it
   works fine from outside.
   ```bash
   dig +short direct.example.com       # your home public IP
   ```

To switch path B off again, remove the `COMPOSE_FILE` line from `.env`, then run
`docker compose up -d --remove-orphans`. That drops the published 80/443 ports and the DDNS
updater. Then remove the router's port forwards.

## 4. Before the interview

- Windows **Power & sleep**: never sleep while plugged in. Docker Desktop: **Start when you
  sign in**. Every container has `restart: unless-stopped`.
- Test both URLs from a phone on mobile data the day before.
- Keep a backup: a screen recording of the demo in case the home network fails.

## Security notes

- Only Caddy is reachable from outside. The API container has no published ports.
- Caddy sets HSTS on path B, plus a strict CSP, `X-Frame-Options`, `nosniff` and a
  referrer policy. It limits request bodies to 6 MB (the API also enforces a 5 MB upload cap).
- The API checks every input against the model's training domain and rate-limits per client IP.
  On path A the client IP comes from `CF-Connecting-IP`. On path B Caddy strips that header,
  so nobody can forge it to dodge the limiter.
- The API container runs as a non-root user, with memory and CPU limits.
- `.env` holds secrets and is git-ignored. Never commit it.

## Troubleshooting

- **`error getting credentials` on `docker pull`/`build` inside WSL.** Docker Desktop's
  credential helper (`credsStore: desktop.exe` in `~/.docker/config.json`) sometimes fails
  from WSL. Public images don't need credentials, so pointing Docker at an empty config for
  the command works around it: `DOCKER_CONFIG=$(mktemp -d) docker compose build`.
- **Optimizer feels slow.** It's CPU-only in the container and should take about 4 s. Check
  `docker stats`. The API is capped at 2 CPUs.
- **Let's Encrypt fails on path B.** Port 80 isn't reaching Caddy (check the forward and the
  firewall), the A record is still proxied (orange cloud), or the ISP blocks port 80.
