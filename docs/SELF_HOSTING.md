# Self-hosting Deep-Foundry

This is the operator runbook for the MVP described in
[ARCHITECTURE.md §8.1](ARCHITECTURE.md#81-self-hosted-dokploy) and
[SECURITY.md §11](SECURITY.md#11-self-hosted-security-posture). Self-hosting
preserves every application security control, while you become responsible for
TLS, network exposure, backups, patching, monitoring, and master-key custody.

## 1. Prepare configuration and secrets

Never commit `infra/.env`. Generate a production file once:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\bootstrap.ps1
```

or:

```sh
./infra/bootstrap.sh
```

The scripts refuse to overwrite an existing file unless explicitly forced. Store
the generated file in an encrypted password manager or secrets system, then set:

- `DJANGO_ALLOWED_HOSTS=agent.example.com`
- `CORS_ALLOWED_ORIGINS=https://agent.example.com`
- `CSRF_TRUSTED_ORIGINS=https://agent.example.com`
- `WEB_APP_URL=https://agent.example.com`
- SMTP values if email notifications should leave the server
- optional Google OAuth credentials

`FIELD_ENCRYPTION_KEY` encrypts provider credentials and MFA secrets. Losing it
makes those values unrecoverable; exposing it compromises every database backup.
Back it up separately from database/object-storage backups. Rotating this key is
not a text-file edit: existing ciphertext must be re-encrypted first.

When `APP_ENV=production`, startup refuses debug mode, placeholder secrets,
wildcard hosts, invalid Fernet keys, and insecure database/object-store passwords.
TLS redirect, secure cookies, proxy HTTPS handling, and one-year HSTS are enabled.

## 2. Recommended deployment: Dokploy

1. Install Dokploy on a patched Linux host and point your domain's DNS record at it.
2. Create a Project, then a **Compose** service using **Docker Compose** (not Stack,
   because this repository builds images from source).
3. Connect the repository and set the Compose path to `./infra/docker-compose.yml`.
4. Paste the generated `infra/.env` content into the Compose Environment editor.
   The compose file references variables explicitly, so they are passed to the
   appropriate services.
5. Deploy. The app runs migrations before becoming healthy; the worker and web
   containers wait for that health check. The `sandboxd` service is privileged
   because it runs a private nested Docker daemon; it never mounts the host Docker
   socket. Verify your host/Dokploy policy permits privileged Compose services.
6. In Domains, route your HTTPS domain to service `web`, container port `3000`.
   Browser API calls are same-origin and the web container proxies them internally
   to `app`; do not publish Postgres, Redis, MinIO, or the app container publicly.
7. Open the domain, register the first user, add a DeepSeek Cloud credential under
   Provider Credentials, create a coworker, and enable MFA for the owner account.

The compose stack deliberately uses `pgvector/pgvector:pg16`; do not replace it
with Dokploy's stock PostgreSQL service. Persistent state uses named volumes, which
allows Dokploy Volume Backups. Dokploy's current Compose and domain workflow is
documented at <https://docs.dokploy.com/docs/core/docker-compose>.

`execute_code` creates an ephemeral child container inside `sandboxd` for each
approved call. Child containers have no network, a read-only root filesystem, no
Linux capabilities, and CPU, memory, PID, time, and output caps. Never expose port
2375 or attach `sandboxd` to a public network. Its image-cache volume is disposable
and does not contain application data.

Research adds `browserd` and `browser-proxy` services. Neither publishes a host
port. `browserd` has no direct external network and can only reach the private
proxy; the proxy is the only component on the research egress network. Keep
`BROWSER_SERVICE_TOKEN`/`INTERNAL_API_TOKEN` private and do not attach `browserd`
to the default application or public gateway network. The Playwright image is
large, so allow extra time and disk space for its first build.

The defaults in `infra/.env.example` bound webpage/document bytes, crawler
pages/depth/duration/cache lifetime, and browser time/text/HTML/request budgets.
Operators may lower these limits for small VPS hosts. Review the SSRF and resource
controls in [SECURITY.md](SECURITY.md#5-sandboxing--code-execution) before raising
them.

## 3. Raw Docker Compose fallback

Install Docker Engine/Compose and place your TLS reverse proxy in front of port
8080. Then:

```sh
docker compose -f infra/docker-compose.yml --env-file infra/.env --profile raw up --build -d
docker compose -f infra/docker-compose.yml --env-file infra/.env ps
curl --fail http://127.0.0.1:8080/health
```

The `raw` profile starts the bundled Traefik gateway for HTTP routing. Production
TLS still belongs at your external reverse proxy. Only ports 80/443 should be
internet-accessible; the database, API, web development port, and MinIO ports bind
to loopback.

## 4. Backups and recovery

Back up all three named volumes and `infra/.env`:

- `postgres_data`: authoritative relational data, audit history, and encrypted secrets
- `minio_data`: uploaded knowledge source objects
- `redis_data`: queued work; useful for continuity but not authoritative

For Dokploy, configure scheduled off-host/S3 Volume Backups for each named volume.
The platform supports automated backup only for named volumes, which is why this
stack does not use host bind mounts for state. Also take a logical PostgreSQL dump
before every upgrade:

```sh
mkdir -p backups
docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/agentarium.dump'
docker compose -f infra/docker-compose.yml --env-file infra/.env cp postgres:/tmp/agentarium.dump ./backups/agentarium.dump
```

Encrypt backups before copying them off-host. Retain multiple generations and test
restores on an isolated host at least quarterly. A backup that has never restored
successfully is not a verified backup.

Restore only into an empty/test database after stopping `app` and `worker`. Keep a
copy of the pre-restore state, restore PostgreSQL and MinIO from the same recovery
point, then run migrations and verify `/health`, login, knowledge retrieval, and an
audit query before reopening traffic.

## 5. Upgrades and operations

1. Read release notes and take verified database/object backups.
2. Pull the tagged release or update the Dokploy source reference.
3. Redeploy; migrations run once in the health-gated app startup.
4. Check `app`, `worker`, and `web` logs and exercise the first-run checklist below.
5. Roll back code only with a schema-compatible release; restore backups when a
   migration is not backward-compatible.

Monitor disk space, container restarts, `/health`, worker queue latency, PostgreSQL,
and certificate expiry. Restrict Docker socket and host SSH access, apply OS and
container updates promptly, and never expose MinIO's console publicly.

## 6. MVP acceptance checklist

- Register and sign in; enable MFA.
- Add a DeepSeek Cloud API credential without exposing it again in the UI or logs.
- Create a coworker and start a chat.
- Save a fact to memory and confirm it remains available in a later conversation.
- Create a knowledge base, upload a document, and wait for `ready` ingestion status.
- Attach the `execute_code` dangerous tool and confirm its call pauses with an
  attributable approval request before any execution; after approval, run a benign
  Python expression and confirm its stdout is shown.
- Attach `web_search` and confirm a query returns titled source links rather than an
  empty placeholder result.
- Attach `read_webpage`, read a public HTML page, and confirm it returns the final
  URL, title, headings, links, and bounded readable text. Confirm a loopback or
  private-network URL is rejected.
- Open Research, run a cited report against a public question, and confirm the
  evidence panel shows URL, title, publication/access dates, and exact passages.
- Crawl a small public site and verify page/depth caps. Create a website monitor,
  run it once for a baseline, and confirm its retained history appears.
- Explicitly enable the JavaScript browser on a test run and confirm `browserd`
  remains internal. Confirm loopback, cloud metadata, and private-address
  destinations are rejected on every fetching path.
- Approve or deny from both inline Chat and the Approval Inbox using only a keyboard.
- Confirm the event appears in Audit and the model call appears in Usage.
- Restart the stack and confirm all persistent data remains.
