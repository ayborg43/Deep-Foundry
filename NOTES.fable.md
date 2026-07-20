# Fable Notes

- 2026-07-20: The existing `ai.web_reader` is the canonical SSRF boundary; new
  document, crawl, monitor, and browser paths must reuse its URL validation
  semantics instead of introducing an independent permissive fetcher.
- 2026-07-20: The frontend is a client-authenticated Next.js App Router app.
  Research progress should use bounded polling against durable database events,
  matching existing background-task behavior without adding a second realtime
  transport.
- 2026-07-20: JavaScript rendering must be a separately deployed browser
  service on an isolated control network and a dedicated egress network, with
  per-request non-persistent contexts and request interception.
- 2026-07-20: Search-provider snippets are discovery hints only. Citations are
  created only from opened pages/documents, bind cited report/message claims to
  a server-retained exact passage, and preserve the server's stable ordinal.
- 2026-07-20: Workspace blocklists are enforced by the shared HTTP boundary on
  initial and redirect destinations and are merged into direct coworker tools,
  deep research, crawls, monitors, and browser subrequests.
- 2026-07-20: Monitor failures remain queued during Celery retry attempts and
  become terminal/notify only on the final attempt.
- 2026-07-20: Verification evidence: 247 Django tests passed from a fresh
  migrated database; targeted ESLint and the Next.js production build passed;
  both Compose files validated; the pinned browser/proxy images built; browserd
  became healthy and fetched Example Domain through the proxy with transfer
  accounting; the direct reader fetched Example Domain; loopback was rejected.
# Telegram notification integration

- Telegram bots cannot initiate a private conversation. A user must open the
  bot and tap Start, so a one-time `t.me/<bot>?start=<token>` link is the
  reliable multi-user linking mechanism.
- Treat Telegram as a user-owned notification channel, not a workspace-shared
  generic integration. Keep delivery preferences scoped to the user and
  workspace.
- Store only a hash of each short-lived start token. Validate Telegram's
  webhook secret and require a private chat whose sender and chat IDs match
  before consuming the token atomically.
- Never accept phone numbers or manually entered chat IDs as routing data.
