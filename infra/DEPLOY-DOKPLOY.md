# Deploying on Dokploy

This stack ships a purpose-built Compose file for [Dokploy](https://dokploy.com):
[`infra/docker-compose.dokploy.yml`](./docker-compose.dokploy.yml). It swaps the
local bundled Traefik `gateway` for Dokploy's shared Traefik (via container
labels), drops all host-port publishing, and takes the public domain + secrets
from Dokploy's Environment editor.

## Prerequisites

- A server with Dokploy installed (`curl -sSL https://dokploy.com/install.sh | sh`).
- A domain with an `A`/`AAAA` record pointing at the Dokploy host.
- Ports 80/443 open — Dokploy's Traefik terminates TLS and routes to the stack.

## 1. Create the service

1. **Project → Create Service → Compose.**
2. **Deploy type must be `Docker Compose`, not `Docker Swarm`.** The `sandboxd`
   code-execution daemon runs `privileged: true` (Docker-in-Docker), which Swarm
   mode does not support.
3. **Provider:** point it at this Git repository (branch of your choice).
4. **Compose Path:** `infra/docker-compose.dokploy.yml`.

## 2. Environment

Open the service's **Environment** tab and paste the contents of
[`.env.dokploy.example`](./.env.dokploy.example), then fill in real values.

At minimum you must set (the deploy fails fast with a clear message otherwise):

| Variable | How to generate |
|---|---|
| `DOMAIN` | your public hostname, e.g. `app.example.com` |
| `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `FIELD_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `INTERNAL_API_TOKEN` | `openssl rand -hex 32` |
| `DB_PASSWORD` | `openssl rand -base64 24` |
| `MINIO_ROOT_PASSWORD` | `openssl rand -base64 24` |

`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`,
`WEB_APP_URL`, and the from-address are **derived from `DOMAIN`** automatically —
only set them if you need something different.

## 3. Domain & TLS

Routing is handled by the Traefik **labels already in the compose file**, so you
do not need to add a domain in Dokploy's UI. They route the single `DOMAIN`:

- `/api`, `/ai`, `/internal`, `/health` → `app` (Django) — priority 100
- everything else → `web` (Next.js) — the browser only ever talks to `web`, which
  proxies API calls to `app` over the internal network
- plain HTTP (`:80`) is 301-redirected to HTTPS

TLS uses the certificate resolver named by `CERT_RESOLVER` (default `letsencrypt`,
which is what a stock Dokploy install configures). If your install uses a
different resolver name, set `CERT_RESOLVER` in the Environment tab.

> Prefer the Dokploy UI instead of labels? Remove the `labels:` blocks from `web`
> and `app`, then add a Domain in the UI pointing at service `web`, port `3000` —
> but you lose the direct `/api` → Django route (Next.js still proxies it, so it
> keeps working, just with an extra hop).

## 4. Deploy

Hit **Deploy**. On first boot the `app` service runs
`python manage.py migrate` automatically before starting, then `worker` and
`beat` (Celery) come up once `app` is healthy.

## Optional Telegram notifications

Create one shared bot with Telegram's `@BotFather`, then set these three
variables together in Dokploy:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The bot token from BotFather |
| `TELEGRAM_BOT_USERNAME` | The bot username without `@` |
| `TELEGRAM_WEBHOOK_SECRET` | 32-256 random URL-safe characters |

After the deployment is healthy, open a terminal in the `app` service and run:

```bash
python manage.py configure_telegram_webhook
```

The command registers
`https://$DOMAIN/api/v1/webhooks/telegram` and does not print either secret.
Users can then connect from **Settings > Notifications** by opening their
single-use Telegram link. They do not enter phone numbers or chat IDs.

## What runs

| Service | Role | Exposed? |
|---|---|---|
| `web` | Next.js frontend + API proxy | via Traefik (`DOMAIN`) |
| `app` | Django ASGI API | via Traefik (`DOMAIN`, API paths) |
| `worker` / `beat` | Celery worker + scheduler | internal |
| `postgres` | Postgres + pgvector | internal |
| `redis` | cache + Celery broker | internal |
| `minio` | S3-compatible object storage | internal |
| `sandboxd` | isolated code-execution DinD | internal (`sandbox_control`, no egress) |

## Notes & caveats

- **Persistence:** `postgres_data`, `redis_data`, `minio_data`, and
  `sandbox_docker_data` are named volumes — Dokploy keeps them across redeploys.
  Add them under the service's **Volumes/Backups** if you want scheduled backups.
- **MinIO is internal.** If the frontend needs to download large artifacts
  directly via presigned URLs, expose the MinIO S3 API on a second subdomain
  (add a `minio` label block + set `MINIO_ENDPOINT` to that URL). Not required for
  the core app to run.
- **`/internal` is reachable on the public domain** (guarded by
  `INTERNAL_API_TOKEN`) so external payment webhooks can reach it — same behavior
  as the bundled `infra/traefik-dynamic.yml`. Keep that token strong.
- **Local development is unchanged** — keep using `infra/docker-compose.yml`
  with the `raw` profile; this file is production-only.

## Validate the compose locally

```bash
docker compose -f infra/docker-compose.dokploy.yml \
  --env-file infra/.env.dokploy.example config
```
(fill the required secrets in a copy first — the `:?` guards reject blanks).
