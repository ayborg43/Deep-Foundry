## API.md

# Agentarium — API Design

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
POST   /api/v1/auth/mfa/verify
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

```
GET    /api/v1/workspaces/{ws}/coworkers
POST   /api/v1/workspaces/{ws}/coworkers
GET    /api/v1/coworkers/{id}
PATCH  /api/v1/coworkers/{id}                      (creates a new coworker_version)
DELETE /api/v1/coworkers/{id}                       (archives, soft-delete)
GET    /api/v1/coworkers/{id}/versions
POST   /api/v1/coworkers/{id}/versions/{v}/rollback

POST   /api/v1/coworkers/{id}/skills                (attach)
DELETE /api/v1/coworkers/{id}/skills/{skill_id}
POST   /api/v1/coworkers/{id}/tools                 (attach)
DELETE /api/v1/coworkers/{id}/tools/{tool_id}
POST   /api/v1/coworkers/{id}/knowledge-bases       (attach)
DELETE /api/v1/coworkers/{id}/knowledge-bases/{kb_id}

GET    /api/v1/coworkers/{id}/analytics?range=30d
```

**Response shape — `Coworker` (illustrative):**
```json
{
  "id": "uuid",
  "name": "Aria",
  "role_description": "Handles customer support triage...",
  "model_binding": { "primary": "deepseek/deepseek-v3", "fallback": ["deepseek/deepseek-r1"] },
  "permission_profile": { "safe": "auto", "sensitive": "approval", "dangerous": "approval" },
  "attached_skills": ["skill_id_1", "skill_id_2"],
  "status": "active",
  "current_version": 4
}
```

## 4. Chat

```
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
POST   /api/v1/conversations/{id}/messages          (send; triggers streamed response)
GET    /api/v1/conversations/{id}/messages/stream    (SSE — token stream + tool-call events)
POST   /api/v1/messages/{id}/regenerate
PATCH  /api/v1/messages/{id}
```

**SSE event types on the stream endpoint:** `token`, `tool_call_started`, `tool_call_result`, `approval_required`, `message_complete`, `error` — the `approval_required` event is what the Chat UI uses to render an inline approval prompt per `SOUL.md` §6.3, without the client needing to poll.

## 5. Memory & Knowledge

```
GET    /api/v1/memory?scope=coworker&scope_id={id}&query=...   (semantic search)
POST   /api/v1/memory
PATCH  /api/v1/memory/{id}
DELETE /api/v1/memory/{id}
GET    /api/v1/memory/{scope}/{scope_id}/timeline

POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{id}
POST   /api/v1/knowledge-bases/{id}/documents        (upload; multipart or URL)
GET    /api/v1/knowledge-bases/{id}/documents/{doc_id}/status
DELETE /api/v1/knowledge-bases/{id}
```

## 6. Agent Teams, Projects & Tasks

```
POST   /api/v1/agent-teams
GET    /api/v1/agent-teams/{id}
PATCH  /api/v1/agent-teams/{id}
POST   /api/v1/agent-teams/{id}/run                  (kick off a team objective)

POST   /api/v1/projects
GET    /api/v1/projects/{id}
POST   /api/v1/projects/{id}/resources               (associate coworker/task/kb/etc.)

GET    /api/v1/tasks?status=needs_approval
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/approve
POST   /api/v1/tasks/{id}/deny
```

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

```
get_coworker_config(coworker_id) -> ResolvedCoworkerConfig
    resolved config: role, model binding, permission profile + org policy floor merged

get_provider_credential(workspace_id, deployment_mode) -> DecryptedCredential
    deployment_mode is deepseek_cloud or deepseek_self_hosted (DATABASE.md §2.7); decrypted at call time, never cached beyond the call

report_task_status(task_id, status) -> None
    AI modules / Celery workers report execution status back to the Core task record

create_approval_request(coworker_id, tool_id, requested_action) -> ApprovalRequest
    created when a dangerous tool call is attempted, from either the ASGI process or a worker

write_audit_log(actor_type, actor_id, action, resource_type, resource_id, metadata) -> None
    every module calls this rather than writing its own log table, per ARCHITECTURE.md §9
```

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
