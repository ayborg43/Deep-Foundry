# Agentarium

Agentarium is a self-hostable AI coworker platform. Phase 2 includes organization
RBAC and policy floors, shared coworkers, multi-agent teams, durable scheduled and
event-driven workflows, a reviewed Marketplace with first-party capability packs,
a publishing SDK, integrations, browser voice controls, a permission-gated desktop
companion, and cloud or self-hosted DeepSeek routing. Approved Python execution
runs in a fresh networkless, resource-limited sandbox container for every call.

Phase 3 adds enterprise SSO/SCIM, delegated governance, residency and SLA policy,
audit anomaly detection and evidence exports, dependency-scored paid Marketplace
packages with creator payouts, portable coworkers, conditional workflows, and
integrity-checked presentation, diagram, and video-analysis artifacts.

## Local quick start

Requirements: Docker Desktop with Compose v2, Linux containers, and enough free
space for the private sandbox daemon. For frontend development outside Docker,
Node.js 22 is also recommended.

```powershell
Copy-Item infra\.env.example infra\.env
docker compose -f infra\docker-compose.yml --env-file infra\.env --profile raw up --build -d
```

The application performs database migrations automatically and waits for healthy
dependencies. Open <http://localhost:8080>. Direct development ports remain
available on loopback at web <http://localhost:3000>, API
<http://localhost:8000>, and MinIO console <http://localhost:9001>.

For a production deployment, do not copy the example secrets. Generate them and
then set your public domain values:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\bootstrap.ps1
```

Linux/macOS:

```sh
./infra/bootstrap.sh
```

Continue with [Self-hosting and Dokploy](docs/SELF_HOSTING.md). It covers TLS,
first-run setup, backups, restore testing, upgrades, and the raw Docker Compose
fallback.

## Development checks

```powershell
docker compose -f infra\docker-compose.yml --env-file infra\.env exec app python manage.py test
Set-Location apps\web
npm.cmd install
npm.cmd run lint
npm.cmd run build
```

The publishing SDK lives in `packages/agentarium-sdk`. The optional Tauri desktop
companion lives in `apps/desktop-companion`; its local capabilities require folder
grants or one-time terminal approvals.

Architecture and product contracts live in [docs](docs/IMPLEMENTATION_PLAN.md).
Security reports should follow [the private disclosure process](docs/SECURITY.md#10-vulnerability-disclosure--incident-response),
not a public issue.
