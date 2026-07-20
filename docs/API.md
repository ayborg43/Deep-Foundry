## API.md

# Deep-Foundry — API Design

> Downstream of `SOUL.md` and `ARCHITECTURE.md` ([Section 3, Application Breakdown](ARCHITECTURE.md#3-application-breakdown)). Defines the external REST surface (web/desktop/third-party SDK clients → API Gateway) and the internal module interface between the Core and AI modules of the application (ARCHITECTURE.md ADR-006). Endpoint lists are representative of MVP scope per `SOUL.md` §6, not exhaustive of V2/V3.

## 1. Conventions

- Base path: `/api/v1/...`. Breaking changes bump to `/api/v2/...`; the platform supports at most two major versions concurrently, with a documented deprecation window (minimum 6 months) before retiring the older one.
- Auth: Bearer JWT (session-derived for web/desktop, long-lived scoped API tokens for the Developer SDK) in the `Authorization` header.
- All list endpoints are cursor-paginated (`?cursor=...&limit=...`), never offset-paginated, to stay stable under concurrent writes.
- All mutating endpoints are idempotent where the client supplies an `Idempotency-Key` header — required for any endpoint that triggers a Task/Workflow execution or a billing charge.
- Errors follow a single envelope: `{ "error": { "code": "string", "message": "string", "details": {} } }` with standard HTTP status codes; `code` is a stable machine-readable string, `message` is human-readable, never the reverse.
- Streaming endpoints (chat, task execution) use Server-Sent Events (SSE) for MVP — simpler client implementation than WebSockets for a predominantly server-to-client streaming pattern; upgrade to WebSockets only if bidirectional low-latency needs emerge (e.g., real-time voice, per `SOUL.md` §6.3 Research item).

## 2. Authentication & Workspace

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
POST   /api/v1/auth/oauth/{provider}/callback
POST   /api/v1/auth/mfa/enroll         (authenticated — generates a TOTP secret, not yet active)
POST   /api/v1/auth/mfa/enroll/confirm (authenticated — first valid code flips mfa_enabled=true)
POST   /api/v1/auth/mfa/verify         (unauthenticated — completes a login that returned mfa_required)
GET    /api/v1/me
PATCH  /api/v1/me

GET    /api/v1/workspaces
POST   /api/v1/workspaces
GET    /api/v1/workspaces/{id}
PATCH  /api/v1/workspaces/{id}
POST   /api/v1/workspaces/{id}/members            (invite)
GET    /api/v1/workspaces/{id}/members
PATCH  /api/v1/workspaces/{id}/members/{member_id} (role change)
DELETE /api/v1/workspaces/{id}/members/{member_id}
POST   /api/v1/workspaces/{id}/provider-credentials
GET    /api/v1/workspaces/{id}/provider-credentials
DELETE /api/v1/workspaces/{id}/provider-credentials/{cred_id}
```

## 3. Coworkers

Built in Milestone 3: coworker CRUD/versioning/rollback, the Tool catalog, and structural tool attachment. `skills`/`knowledge-bases` attach endpoints and `/analytics` stay listed below as the documented target shape but aren't implemented until Milestone 5 (Skills/Knowledge) and later (analytics) respectively — SOUL.md §6 marks both later-than-MVP.

```
GET    /api/v1/tools                                (the platform-wide Tool catalog, DATABASE.md §2.3 —
                                                       not in the original Phase 1 list; added because an
                                                       attach-a-tool UI needs to know what's attachable)

GET    /api/v1/workspaces/{ws}/coworkers
POST   /api/v1/workspaces/{ws}/coworkers
GET    /api/v1/coworkers/{id}
PATCH  /api/v1/coworkers/{id}                      (role_description/model_binding changes create a new
                                                     coworker_version; name/avatar_url do not)
DELETE /api/v1/coworkers/{id}                       (archives, soft-delete)
GET    /api/v1/coworkers/{id}/versions
POST   /api/v1/coworkers/{id}/versions/{version_number}/rollback
                                                     (creates a NEW version copying the target version's
                                                      content — rollback is itself a recorded version, not
                                                      a destructive pointer move)

POST   /api/v1/coworkers/{id}/skills                (V2 — Developer SDK/Marketplace)
DELETE /api/v1/coworkers/{id}/skills/{skill_id}     (V2 — Developer SDK/Marketplace)
POST   /api/v1/coworkers/{id}/tools                 (attach; body: { tool_id, config?, enabled? } —
                                                      idempotent, re-attaching updates config/enabled)
DELETE /api/v1/coworkers/{id}/tools/{tool_id}
POST   /api/v1/coworkers/{id}/knowledge-bases       (attach; body: { knowledge_base_id })
DELETE /api/v1/coworkers/{id}/knowledge-bases/{kb_id}

GET    /api/v1/coworkers/{id}/analytics?range=30d   (not yet implemented — SOUL.md §8, V2)
```

**Response shape — `Coworker`:**
```json
{
  "id": "uuid",
  "name": "Aria",
  "avatar_url": null,
  "role_description": "Handles customer support triage...",
  "model_binding": { "primary": "deepseek-v4-flash", "fallback": ["deepseek-v4-pro"] },
  "permission_profile": { "safe": "auto", "sensitive": "approval", "dangerous": "approval" },
  "attached_tools": [ { "id": "uuid", "name": "web_search", "enabled": true } ],
  "status": "active",
  "current_version": 4,
  "created_at": "2026-07-13T00:00:00Z"
}
```
`model_binding.primary`/`fallback` values must be DeepSeek model IDs the Model Router actually accepts — `deepseek-v4-flash` or `deepseek-v4-pro` (`ai/model_router/adapters/deepseek_cloud.py`). `attached_skills` from the original illustrative example is dropped until Milestone 5 — `attached_tools` covers what Milestone 3 actually attaches.

## 4. Chat

```
GET    /api/v1/conversations?workspace_id={id}
POST   /api/v1/conversations                          ({workspace_id, coworker_id, title?})
GET    /api/v1/conversations/{id}
GET    /api/v1/conversations/{id}/messages             (history, not streamed)
POST   /api/v1/conversations/{id}/messages             (send; SSE response inline on this request — see below)
GET    /api/v1/conversations/{id}/messages/stream       (SSE — resumes a turn paused on approval_required)
POST   /api/v1/messages/{id}/regenerate                 (SSE, same event shape as send)
PATCH  /api/v1/messages/{id}                            ({content} — user's own messages only, no reprocessing)
```

`GET .../messages` (plain JSON history) was added in Milestone 4 alongside the rest of this section — a client needs some way to load history on open/reconnect that isn't itself an SSE connection.

**Streaming transport, Milestone 4's actual implementation:** `POST /conversations/{id}/messages` and `POST /messages/{id}/regenerate` stream their SSE response directly on that same HTTP request/response — there's no decoupled job-then-poll step. If the turn hits `approval_required`, the stream ends there; once `POST /approval-requests/{id}/approve` (or `/deny`) has been called, the client opens `GET /conversations/{id}/messages/stream` to receive the continuation (the coworker's follow-up response). Approve/deny themselves are plain synchronous JSON endpoints — they decide the request and, if the tool was approved, execute it, but they do not stream; the model's next reply only comes from the `GET .../stream` reconnect.

**SSE event types:** `token` (`{delta}`), `tool_call_started` (`{tool_name, arguments, message_id}`), `tool_call_result` (`{tool_name, result, message_id}`), `approval_required` (`{approval_request_id, tool_name, arguments, message_id}` — what the Chat UI uses to render an inline approval prompt per `SOUL.md` §6.3, without polling), `message_complete` (`{content}`), `error` (`{detail}`).

Completed assistant messages may include `citations[]`. Each citation contains a
stable ordinal, source URL/title/publisher, publication and access dates, exact
supporting passage, and document locator/page number when available.

### Research and monitoring

```text
GET|POST /api/v1/research-runs
GET|PATCH /api/v1/research-runs/{id}                 (PATCH {cancel:true})
GET       /api/v1/research-runs/{id}/sources
GET       /api/v1/research-runs/{id}/exports/{json|csv|markdown}

GET|POST   /api/v1/website-monitors
GET|PATCH|DELETE /api/v1/website-monitors/{id}
POST       /api/v1/website-monitors/{id}/run
GET        /api/v1/website-monitors/{id}/history

GET|PUT /api/v1/workspaces/{workspace_id}/research-policy
```

Research creation accepts `mode: deep|crawl|extraction`, a question or starting
URL, an optional coworker, and bounded controls for source diversity, recency,
language/country, trusted/blocked domains, crawl pages/depth/rate, explicit
browser rendering, and a shallow extraction schema. Runs are Celery-backed and
return immediately with durable status and progress. All endpoints enforce
workspace membership.

**Approval gate endpoints**, per `SECURITY.md` §4:
```
GET    /api/v1/workspaces/{workspace_id}/approval-requests?status=pending
POST   /api/v1/approval-requests/{id}/approve
POST   /api/v1/approval-requests/{id}/deny
```
Any member of the coworker's workspace may decide a pending request for MVP — SECURITY.md §4's "who specifically can grant approval" configurability is a later refinement, not built yet. Deciding an already-decided request returns `400`, not a silent success — see `core.interface.ApprovalRequestAlreadyDecidedError`.

## 5. Memory & Knowledge

```
GET    /api/v1/memory?scope=coworker&scope_id={id}&query=...   (semantic search)
POST   /api/v1/memory
PATCH  /api/v1/memory/{id}
DELETE /api/v1/memory/{id}
GET    /api/v1/memory/{scope}/{scope_id}/timeline

POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases?workspace_id={id}
GET    /api/v1/knowledge-bases/{id}
POST   /api/v1/knowledge-bases/{id}/documents        (upload; multipart or URL)
GET    /api/v1/knowledge-bases/{id}/documents/{doc_id}/status
DELETE /api/v1/knowledge-bases/{id}
```

`POST /knowledge-bases` accepts `{workspace_id, name, scope, scope_id}`. Document upload uses multipart form data with a `file` part (PDF, text, or Markdown; 25 MB maximum), returns `202`, and queues ingestion. The detail response includes `documents[]` with `ingestion_status`/`ingestion_error` and `attached_coworker_ids`; the list response omits documents. Coworker attachment uses the endpoints in §3 with body `{knowledge_base_id}`.

## 6. Agent Teams, Projects & Tasks

```
POST   /api/v1/agent-teams
GET    /api/v1/agent-teams/{id}
PATCH  /api/v1/agent-teams/{id}
POST   /api/v1/agent-teams/{id}/run                  (kick off a team objective)

POST   /api/v1/projects
GET    /api/v1/projects/{id}
POST   /api/v1/projects/{id}/resources               (associate coworker/task/kb/etc.)

GET    /api/v1/tasks?workspace_id={id}&status=needs_approval
POST   /api/v1/tasks                                ({workspace_id, coworker_id, title, description,
                                                      due_at?, project_id?}; returns 202)
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/approve
POST   /api/v1/tasks/{id}/deny
POST   /api/v1/conversations/{id}/tasks             (chat handoff; coworker/workspace derived from conversation)

GET    /api/v1/notifications?unread=true
PATCH  /api/v1/notifications/{id}/read
```

Task responses include `status`, `result`, `error_message`, timestamps, and the assigned `coworker_name`. Creation queues a Celery job and returns immediately. A task paused on a tool call has `status=needs_approval`; either the task decision endpoints or the general approval-request endpoints may decide it, and both enqueue the same durable continuation. Denial transitions the task to `blocked`; completion or failure produces a `task_completed` notification whose payload carries the terminal status.

## 7. Workflows

```
POST   /api/v1/workflows
GET    /api/v1/workflows/{id}
PATCH  /api/v1/workflows/{id}                        (new version)
POST   /api/v1/workflows/{id}/triggers
POST   /api/v1/workflows/{id}/run                    (manual trigger)
GET    /api/v1/workflows/{id}/runs
GET    /api/v1/workflow-runs/{run_id}
POST   /api/v1/workflow-runs/{run_id}/steps/{step_id}/approve
```

## 8. Marketplace

```
GET    /api/v1/marketplace/listings?type=skill&query=...
GET    /api/v1/marketplace/listings/{id}
POST   /api/v1/marketplace/listings                  (publish; requires review before listed)
POST   /api/v1/marketplace/listings/{id}/versions
POST   /api/v1/marketplace/listings/{id}/install
POST   /api/v1/marketplace/listings/{id}/fork
POST   /api/v1/marketplace/listings/{id}/reviews
GET    /api/v1/marketplace/listings/{id}/reviews
```

Every `install` response includes the full permission manifest of what's being granted (tool risk classes the skill declares) so the client can render the consent screen described in `SOUL.md` §10.5 *before* the install call is even made — the client fetches `GET /listings/{id}` (which includes `declared_tools`) to build that screen, then calls `install` only after explicit user consent.

## 9. Admin & Audit

```
GET    /api/v1/workspaces/{ws}/audit-log?from=...&to=...
GET    /api/v1/workspaces/{ws}/usage?range=30d
GET    /api/v1/workspaces/{ws}/policy-floors
POST   /api/v1/workspaces/{ws}/policy-floors
```

The audit endpoint is owner/admin-only and accepts `action`, `resource_type`,
`coworker_id`, `offset`, and `limit` in addition to the ISO-8601 date filters.
It returns newest-first `{count, next_offset, results}` data. The usage endpoint
is also owner/admin-only; `range` accepts `1d` through `365d` and returns totals,
daily cost, and breakdowns by coworker and provider/model. Its data is aggregated
directly from `model_calls`, so no second usage ledger can drift from execution.

Internal processes may append an event with `POST /internal/v1/audit-log` using
`X-Internal-Token: <INTERNAL_API_TOKEN>`. This endpoint only inserts; PostgreSQL
rejects every update or delete against `audit_log`.

## 10. Desktop Companion Bridge

The Desktop Companion authenticates as a normal client and calls the same `/api/v1/...` surface for anything server-side (conversations, tasks). Purely local capabilities (clipboard, local file listing before upload, local terminal execution) are handled by a **local-only loopback API** (`http://127.0.0.1:<companion_port>/local/v1/...`) that never leaves the machine, invoked by the Companion's own renderer — this is documented here because the permission-consent contract (what capability is being requested, in what scope) mirrors the same manifest shape used by Marketplace skill installs, per `SOUL.md` §14.

```
POST   /local/v1/fs/read              (scoped to granted folders only)
POST   /local/v1/fs/write
POST   /local/v1/terminal/propose     (returns a diff/preview, does not execute)
POST   /local/v1/terminal/execute     (requires prior propose + explicit approval token)
GET    /local/v1/clipboard
POST   /local/v1/clipboard
```

## 11. Webhooks (inbound, for integrations & event-triggered workflows)

```
POST   /api/v1/webhooks/{integration}/{workspace_token}
```
Verified via per-integration signature validation (e.g., GitHub's `X-Hub-Signature-256`); routed internally to the Workflow Engine's event-trigger evaluator per `ARCHITECTURE.md` §6.

## 12. Internal Module Interface — Core ↔ AI

Not an HTTP API for MVP. Per `ARCHITECTURE.md` ADR-006, Core and AI modules run in the same process (modular monolith) and this is a documented Python interface — service-layer functions/classes called in-process — not a network call, and Celery workers (which import the same codebase) call it exactly the same way the ASGI process does. It's specified here with endpoint-shaped signatures anyway, because it's the seam the system is designed to cut along if the AI modules are ever extracted into their own deployed service (`ARCHITECTURE.md` §10): at that point these become real authenticated HTTP endpoints with the same contract, not a redesign.

**Core → AI direction** (`core.interface`, called by AI modules and Celery workers to reach Core-owned data):

```
get_coworker_config(coworker_id) -> ResolvedCoworkerConfig
    resolved config: role, model binding, permission profile. Graduated in Milestone 4 now that
    Coworker/CoworkerVersion/PermissionProfile exist; org policy floor merge is not yet
    implemented (org_policy_floors has no model — not in Milestone 4's scope, see ARCHITECTURE.md §3.1 note).

get_attached_tools(coworker_id) -> list[ToolInfo]
get_tool_by_name(name) -> ToolInfo | None
    resolved coworker_tool_attachments / tools rows, so callers never import core.models directly

get_provider_credential(workspace_id, deployment_mode) -> DecryptedCredential
    deployment_mode is deepseek_cloud or deepseek_self_hosted (DATABASE.md §2.7); decrypted at call time, never cached beyond the call

get_task_record(task_id) -> TaskRecord
claim_task_execution(task_id) -> TaskRecord | None
report_task_status(task_id, status, *, execution_state=None, result=None, error_message=None) -> None
    durable Task Engine state seam; claim is atomic so duplicate Celery deliveries are no-ops

notify_workspace(workspace_id, notification_type, payload) -> list[notification_id]
    persists one in-app notification per workspace member and enqueues retryable email delivery

create_approval_request(coworker_id, tool_id, requested_action, *, conversation_id=None, message_id=None,
                         task_id=None, workflow_run_step_id=None) -> ApprovalRequest
    persists a pending approval_requests row; exactly one of task_id/workflow_run_step_id/message_id
    must be given (DATABASE.md §2.3) — enforced here, not trusted from the caller

get_approval_request(approval_request_id) -> ApprovalDecision
get_approval_request_for_tool_call(message_id, tool_call_id) -> ApprovalDecision | None
    the chat orchestrator's idempotency check — "has this specific tool call already got a decision?"

decide_approval_request(approval_request_id, *, approve, decided_by_user_id) -> ApprovalDecision
    atomic (select_for_update); raises ApprovalRequestAlreadyDecidedError on a non-pending request,
    so two concurrent decisions on the same request can't both succeed

write_audit_log(actor_type, actor_id, action, resource_type, resource_id, metadata=None, *, workspace_id=None) -> AuditLog
    every module calls this rather than writing its own log table, per ARCHITECTURE.md §9;
    workspace_id is nullable — not every event is scoped to exactly one workspace
```

**AI → Core direction** (`ai.interface`, added Milestone 4 — the first time Core needed to call *into* AI; mirrors `core.interface` the other way, per `ARCHITECTURE.md` §3.1's "Core never imports AI internals except through interface"):

```
start_turn(*, conversation_id, coworker_id, workspace_id, user_id, content) -> Iterator[ChatEvent]
    creates the user Message, then runs the model/tool-call loop until it completes or pauses on
    an approval_required event

resume_turn(*, conversation_id, coworker_id, workspace_id) -> Iterator[ChatEvent]
    re-enters the same loop after an approval decision — discovers what changed from the database,
    not from any in-memory turn state (there isn't any)

regenerate_turn(*, conversation_id, coworker_id, workspace_id, target_message_id) -> Iterator[ChatEvent]
    re-runs the model against history up to (not including) target_message_id, producing a new
    sibling response linked via parent_message_id — the original is left untouched
```

Deliberate, narrow exception: Core's chat views (`core/chat_views.py`) import `ai.models.Conversation`/`Message` directly for plain listing/reading — no business rule to bypass there, unlike send/resume/regenerate, which stay behind `ai.interface` because that's where the approval gate actually lives (`SECURITY.md` §4).

## 13. Developer SDK API Surface

Supports `SOUL.md` §5.12. The SDK is a thin client wrapping:
```
POST   /api/v1/sdk/skills/validate      (local manifest validation against the current schema version)
POST   /api/v1/sdk/skills/publish
GET    /api/v1/sdk/tools/schema          (fetch the current Tool input/output schema catalog for local dev/test harness use)
```

## 14. Rate Limiting

Default tiers enforced at the API Gateway: `60 req/min` per user for standard endpoints, `10 req/min` for expensive endpoints (marketplace publish, knowledge ingestion trigger), configurable per-workspace for cloud enterprise plans. Model-call-triggering endpoints are additionally subject to the workspace's own provider-level rate limits, surfaced back to the client as a distinguishable `429` error code (`rate_limited_platform` vs. `rate_limited_provider`) so the UI can explain *why* accurately.

## 15. Versioning & Deprecation Policy

A field or endpoint is never silently removed. Deprecation follows: announce in changelog + `Deprecation` response header → minimum 6-month overlap window → removal only in a new major version path. This applies equally to the Marketplace manifest schema (per `SOUL.md` §10.5, skill version bumps required for breaking permission changes) and the general API.

## 16. Model Router Internal Test Harness (Milestone 2)

Not the product chat API — that's `/api/v1/conversations/...` in [Section 4](#4-chat), which doesn't exist until Milestone 4 once Coworkers exist. This is the surface `IMPLEMENTATION_PLAN.md` Milestone 2's exit criteria calls for: a way to drive the Model Router end to end (capability negotiation, fallback, streaming, `model_calls` logging) before there's a Coworker to hang it off of. Superseded, not necessarily removed, once real chat endpoints land — a legitimate internal caller (e.g. a future admin "test this credential" button) could still want it.

Served by the AI modules directly (mounted at `/ai/*`, `ARCHITECTURE.md` §3.1), not proxied through `/api/v1/`:

```
POST   /ai/internal/generate
    body: { workspace_id, model_id, messages: [{role, content, tool_call_id?, name?}],
            tools?: [{name, description, parameters}], temperature?, max_tokens?,
            fallback_model_id? }
    200: { content, tool_calls: [{id, name, arguments}], usage: {input_tokens, output_tokens} | null,
           model_id, finish_reason }
    400: capability violation (e.g. unknown model_id) or validation error
    424: no deployment_mode=deepseek_cloud ProviderCredential configured for workspace_id
    429: DeepSeek rate-limited and no fallback_model_id configured
    502: DeepSeek adapter error and no fallback_model_id configured

POST   /ai/internal/generate/stream
    same body as above (model_config.stream is forced true regardless of what's sent)
    200: text/event-stream — `event: chunk` frames shaped like
         { delta, finish_reason, usage } (usage only populated on the final chunk),
         or `event: error` with { detail } if the stream fails mid-flight
```

Both require `Authorization: Bearer <access>` and workspace membership, enforced natively in FastAPI (`ai/dependencies.py`) against the same JWTs and the same `WorkspaceMember` rule as the DRF-served endpoints — one Security & Permissions rule, two entrypoints, per `ARCHITECTURE.md` §7. No fallback on the streaming path: once bytes have reached the client, silently swapping models mid-stream would contradict the Router's normalization goal (`ARCHITECTURE.md` §5) — a stream failure surfaces as an `error` event instead.

## 17. Phase 4 adaptive collaboration endpoints

- `GET|POST /workspaces/{id}/capability-proposals` lists or creates inert tool/
  installed-skill requests. `POST /capability-proposals/{id}/decision` accepts
  `approve` or `deny`; only an Owner/Admin may decide, and attachment happens
  atomically with an approved decision.
- `GET|POST /workspaces/{id}/memory-conflicts` lists, scans (`?scan=true`), or
  manually reports two workspace memories. `POST /memory-conflicts/{id}/resolve`
  accepts `keep_left`, `keep_right`, or `merge` plus `merged_content`.
- `GET|POST /agent-teams/{id}/consensus` lists or starts durable voting sessions;
  `GET /consensus-sessions/{id}` returns attributed votes and the decided or
  deadlocked result. Methods are `majority`, `unanimous`, and
  `confidence_weighted`.
- `GET|POST /voice-sessions`, `GET|PATCH /voice-sessions/{id}`, and
  `POST /voice-sessions/{id}/turns` manage private live-voice transcripts. A turn
  may return `complete`, `needs_approval`, or `failed`; approvals remain in the
  normal approval inbox and are never bypassed by voice mode.
## 13. Phase 3 enterprise endpoints

All endpoints use the existing `/api/v1` envelope and workspace membership
checks unless noted otherwise.

- `GET|PATCH /workspaces/{id}/enterprise` — residency, retention, legal hold,
  support tier, uptime and response targets.
- `GET|POST /workspaces/{id}/sso-providers`, `GET /sso/{id}/login`,
  `POST /sso/{id}/callback` — OIDC and signed SAML-broker SSO with JIT access.
- `GET|POST /workspaces/{id}/scim-tokens`, `GET|POST /scim/v2/Users`,
  `PATCH|DELETE /scim/v2/Users/{id}` — SCIM 2.0 lifecycle provisioning.
- `GET|POST /workspaces/{id}/policy-rules` — ordered allow/deny/approval rules.
- `GET|PATCH /workspaces/{id}/audit-anomalies` and
  `GET|POST /workspaces/{id}/compliance-exports` — anomaly triage and evidence.
- `POST /coworkers/{id}/export` and
  `POST /workspaces/{id}/coworkers/import` — privacy-preserving portable bundles.
- `GET|POST /artifacts` — presentation, diagram, video-analysis, coworker, and
  compliance artifacts with SHA-256 integrity checks.
- `POST /marketplace/listings/{id}/checkout`,
  `POST /marketplace/payment-webhook`, and
  `GET|POST /workspaces/{id}/payout-account` — external payment bridge and
  creator payout ledger.

SCIM calls authenticate with revocable `scm_` bearer tokens. Payment completion
webhooks authenticate with `X-Deep-Foundry-Payment-Signature`, the lowercase hex
HMAC-SHA256 of the exact request body. SAML-broker callbacks use a signed,
ten-minute state token and an HMAC over canonical assertion JSON, then validate
issuer, audience, and allowed email domains.
