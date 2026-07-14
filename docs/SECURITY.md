## SECURITY.md

# Agentarium — Security Architecture

> Expands `SOUL.md` [Section 15](SOUL.md#15-security) and `ARCHITECTURE.md` [Section 7](ARCHITECTURE.md#7-security-boundary-placement). This document is the operative security policy: every threat below maps to a specific control, and every control maps back to a principle in `SOUL.md` §3.

## 1. Threat Model

Agentarium's core risk is unique among SaaS products: it grants autonomous entities (coworkers) the ability to take real-world action — send communications, execute code, spend money, modify files. The threat model is therefore organized around **who or what could cause unwanted action**, not just around traditional data-breach vectors.

| Actor | Risk | Primary control |
|---|---|---|
| Malicious/compromised third-party Skill | A marketplace skill requests broad tool access, then abuses it once installed | Manifest-declared permissions + explicit consent screen + sandboxed tool execution |
| A coworker acting on ambiguous/adversarial user input (prompt injection via a document, email, or web page it reads) | The coworker is manipulated into taking an unintended dangerous action | Approval gates on `dangerous` tools regardless of what triggered the call — the gate doesn't trust the coworker's own judgment for irreversible actions |
| A malicious org member | Escalates privilege, exfiltrates workspace data, tampers with audit logs | RBAC, org policy floors, append-only audit log |
| External attacker | Credential theft, API abuse, data exfiltration | Standard auth hardening, encrypted secrets, rate limiting, sandboxed execution with no default egress |
| A buggy (not malicious) workflow or skill | Runaway loops, unbounded cost, accidental data deletion | Execution budgets, soft-delete/reversibility, idempotent retries |

## 2. Authentication

- Password hashing via a modern, salted, memory-hard algorithm (Argon2id).
- OAuth (Google/GitHub/Microsoft) and, for enterprise, SAML/SSO — see `SOUL.md` §6.1.
- MFA (TOTP at MVP, WebAuthn/passkeys as a V3+ upgrade) available to all users, **mandatory** for workspace Owner/Admin roles on any workspace with `dangerous`-tool-using coworkers configured for autonomous execution beyond default (a deliberate friction point, not an oversight).
- Session tokens are short-lived JWTs with refresh-token rotation; refresh tokens are revocable per-device from the user's settings.
- Developer SDK API tokens are scoped (read-only vs. publish-capable) and independently revocable from session auth.

## 3. Authorization

- **RBAC tiers:** Owner > Admin > Member > Guest at the workspace/org level, with resource-level overrides (a Guest can be scoped to exactly one Project).
- **Single evaluation point:** All authorization checks — RBAC role, resource ownership, permission profile, org policy floor — flow through one Security & Permissions library, called identically from the Core modules, the AI modules, and the Celery worker entrypoint (`ARCHITECTURE.md` §7) — all three run the same codebase, so this is one library called three ways, not three separately implemented checks. No module implements its own ad hoc permission check.
- **Org policy floors are non-negotiable at the coworker level:** an Admin can raise the minimum required approval strictness for a tool risk class org-wide; no individual coworker configuration, skill, or workflow can lower it below that floor. Enforced at evaluation time (`max(strictness)` computation per `DATABASE.md` §4), not at config-save time, so a floor change applies retroactively and immediately.

## 4. The Permission & Approval System

This is Agentarium's central trust mechanism and deserves restating precisely from `SOUL.md` §15.2:

- **Risk classification is a property of the Tool, not the coworker.** `safe` / `sensitive` / `dangerous`, assigned at Tool registration (built-in tools classified by the core team; marketplace/skill-bundled tools classified during the review pipeline in §7).
- **`dangerous` tools always require human approval.** There is no code path, coworker setting, org override, or workflow flag that can set a `dangerous` tool to auto-execute. This is enforced in the Security & Permissions library itself (a hard-coded invariant, not a configurable default) — the only thing configurable is *who* can grant the approval and whether a narrowly-scoped recurring pre-approval exists for one specific action pattern (e.g., "always allow sending to this exact email template to this exact recipient list").
- **Approval is a first-class execution step** (`ARCHITECTURE.md` §6), not a UI-layer convenience — it exists in the Task/Workflow state machine, so an approval requirement can never be silently bypassed by a code path that forgets to check.
- **Every approval decision is attributed and logged** (`approval_requests.decided_by`, `DATABASE.md` §2.3) — approvals are not anonymous or ambient.
- **Prompt injection defense:** because approval gates trigger on the *tool being called*, not on the coworker's stated intent or confidence, a coworker manipulated by adversarial content into attempting a dangerous action still hits the same approval gate a legitimately-instructed coworker would — injection can waste a human's time by generating a bogus approval request, but it cannot itself execute the dangerous action.

## 5. Sandboxing

The Phase 1 self-hosted implementation uses a dedicated Docker-in-Docker daemon
on a private Compose control network. The application does not receive the host's
Docker socket. Each approved Python call is created through the daemon API as a
new child container and is force-removed after completion or timeout.

- Every Tool call that executes code or shell commands runs in an ephemeral, isolated container/microVM, provisioned per call — whether triggered synchronously from a live chat request in the application process or asynchronously by a Celery worker running a Task/Workflow step — and destroyed immediately after (`ARCHITECTURE.md` §7).
- **Default-deny network egress.** A sandbox has zero outbound network access unless the specific Tool's manifest declares a required egress target (e.g., a `web_search` tool is allowlisted to the search provider's API only).
- **Resource limits:** CPU, memory, execution time, and disk are capped per sandbox invocation; a runaway process is killed and reported as a failed Tool call, not left to consume resources indefinitely.
- **No sandbox-to-sandbox communication** and no access to the host's credentials, other workspaces' data, or the platform's own internal network by default.
- The controller daemon requires a privileged container on the self-hosted host;
  its TCP API must never be published. This isolates child-container control from
  the host daemon while keeping the privileged controller itself inside the
  operator's infrastructure trust boundary.

## 6. Secrets Management

- Provider API keys and integration OAuth tokens are envelope-encrypted at rest (`DATABASE.md` §2.7 `provider_credentials.encrypted_key`), decrypted only transiently by the AI modules at call time — whether invoked in-process during a live chat request or by a Celery worker — never logged, never returned to any client in plaintext after initial entry.
- MVP: application-layer envelope encryption keyed by a platform master key (itself stored in a managed KMS for cloud, or an operator-supplied key file for self-hosted).
- V2+ upgrade path: dedicated secrets manager (e.g., Vault) for cloud/enterprise deployments requiring key rotation policies and finer-grained access auditing than envelope encryption alone provides — self-hosted deployments retain the simpler file-key model as a supported, documented option so operating Agentarium doesn't require operating Vault.
- Self-hosted operators are documented and defaulted toward: never committing `.env`/credential files to version control, rotating the master key on a defined schedule, restricting database backup access (backups contain encrypted secrets — encrypted, but still a target).

## 7. Marketplace Security Review Pipeline

Every submitted Skill/Capability Pack/Workflow/Tool listing passes through, before becoming publicly listed:

1. **Automated manifest validation:** declared tools match actual tool calls the instruction content references; no undeclared permission requests.
2. **Automated static scan:** for any bundled code (Tool implementations, not prompt-only Skills), a static security scan for known-dangerous patterns (arbitrary code execution without sandboxing, hardcoded credentials, obfuscated payloads).
3. **Human review** for: any listing requesting `dangerous`-classified tools, any paid listing, any listing seeking "verified publisher" status.
4. **Post-publish monitoring:** install-time consent screens double as a distributed detection mechanism — a listing whose declared permissions change unexpectedly between versions, or that accumulates review reports flagging unexpected behavior, is subject to re-review and can be delisted/quarantined pending investigation.

Unlisted/org-private skills skip the marketplace review queue (they aren't publicly discoverable) but are still subject to the same manifest-validation and sandboxing controls at install/execution time — review gates public discovery, not baseline safety.

## 8. Audit Logging

- `audit_log` (`DATABASE.md` §2.3) is append-only at both layers: application code exposes no mutation path and a PostgreSQL trigger rejects every `UPDATE` or `DELETE`, including direct ORM/SQL attempts. Retention deletion requires an explicit privileged migration that removes the guard.
- Captures: every tool call, every model call (via `model_calls`), every approval decision, every permission/policy change, every RBAC role change, every marketplace install.
- Exportable by workspace Owners/Admins for compliance purposes (`GET /api/v1/workspaces/{ws}/audit-log`, `API.md` §9).
- Retention is workspace-configurable but has a platform-enforced minimum (default 90 days) that cannot be set to zero — an org cannot use the retention setting to make its own audit trail disappear on demand.

## 9. Data Privacy

- Per `SOUL.md` §3 principle 9: workspace data (memory, conversations, knowledge bases) is never used to train shared/foundation models without explicit, revocable, opt-in consent, workspace-by-workspace.
- Model provider calls pass only the minimum context required for the specific request (relevant memory/knowledge retrieved via semantic search, not a full history dump) — both a cost optimization and a privacy-minimization practice.
- Self-hosted deployments have zero platform telemetry by default beyond what's required for license validation (if any) and opt-in anonymous usage stats; cloud deployments document exactly what operational telemetry is collected in a public data-handling policy.
- Right to deletion: a workspace can request full data deletion; per `DATABASE.md` §6, this respects the soft-delete/undo window before hard deletion executes, communicated clearly to the requester so "delete" doesn't silently mean "gone forever with no recourse for 30 days is actually the safety net, not the delay."

## 10. Vulnerability Disclosure & Incident Response

- A documented responsible-disclosure process (security contact, expected response SLA) is published alongside the open source repository from MVP launch — a security-sensitive product without a disclosure path is a liability from day one, not a V2 nicety.
- Incident response plan (for the hosted cloud offering) defines: detection (audit log anomaly monitoring, per `SOUL.md` §6.11 V3 "anomaly detection" item, is the long-term direction; MVP relies on standard infra alerting), containment (workspace-level credential revocation/coworker suspension capability for platform operators in a confirmed-compromise scenario), and disclosure timeline commitments to affected workspaces.

Report vulnerabilities through the repository host's private vulnerability-reporting form (GitHub: **Security → Report a vulnerability**). Do not include exploit details in a public issue. Maintainers acknowledge reports within three business days, provide a triage/status update within seven days, coordinate remediation and disclosure with the reporter, and credit reporters who opt in. If private reporting is unavailable, contact a maintainer privately and request a secure reporting channel before sending sensitive details.

## 11. Self-Hosted Security Posture

Because self-hosted deployments run the identical codebase (`SOUL.md` §4.26, `ARCHITECTURE.md` §8.1), every control in this document applies equally there — self-hosting is not a reduced-security mode. The operator takes on responsibility for infrastructure-level controls (TLS termination, network isolation, database backup security, master key custody) that the cloud offering handles on the operator's behalf; the application-layer controls (permission system, sandboxing, audit logging) are identical and not configurable-away.

The supported bootstrap and operations procedure is [SELF_HOSTING.md](SELF_HOSTING.md). Production mode fails closed on debug mode, placeholder secrets, wildcard hosts, invalid master keys, and default database/object-store passwords. Operators must keep the generated master key separately recoverable, schedule encrypted off-host backups for PostgreSQL and MinIO, test restores, expose only TLS entrypoints, and enable MFA on owner/admin accounts.

## 12. Security Principles Recap

Every control above exists to serve one of these; when a new feature raises a security question not explicitly covered here, resolve it against these:

1. Dangerous actions are never fully autonomous, ever, by design that cannot be configured away.
2. Every action a coworker takes is attributable, logged, and explainable after the fact.
3. Self-hosted is not a lesser security tier.
4. Trust is granted explicitly (consent screens, manifest declarations) and revocable, never ambient.
5. A compromised or malicious third-party Skill is contained by sandboxing and the approval gate, not by trusting the review pipeline as the only line of defense.
## 12. Phase 3 enterprise controls

- Delegated enterprise roles are capability-mapped; a security administrator
  cannot manage billing and a billing administrator cannot change SSO or policy.
- SCIM and SDK credentials are separately hashed, scoped, revocable tokens. Their
  plaintext value is returned only at creation.
- OIDC uses authorization-code exchange. The SAML integration trusts only a
  configured identity gateway that has already validated XML signatures; the
  gateway assertion is independently protected by signed state and HMAC, and
  Agentarium validates issuer, audience, domain, and freshness.
- Organization rules are evaluated in priority order and enforced at all three
  tool execution entrypoints: interactive chat, background tasks, and workflows.
- Compliance and portable-coworker exports exclude encrypted credentials,
  integration secrets, private memory, and tool configuration. Canonical export
  content is protected with SHA-256 for later evidence verification.
- Payment and incoming integration webhooks use constant-time HMAC comparison.
  Paid packages are not installed until a signed completion event marks an order
  paid. Creator proceeds are an append-only ledger derived from the paid order.
- Conditional workflows support a fixed declarative operator set and never pass
  policy or workflow expressions to `eval`, a shell, or a model for execution.

## 13. Phase 4 adaptive controls

- Capability proposals are non-authorizing records. Only workspace Owners/Admins
  can approve, and an installed skill or existing tool is revalidated inside the
  same database transaction before attachment. Duplicate/open review races lock
  the proposal row and fail closed.
- `propose_capability` is classified safe because it grants nothing; any later
  tool execution still uses that tool's own risk class and normal approval rules.
- Consensus output is advisory and auditable. Every vote is attributed to a
  coworker and task; invalid output produces no vote, and ties/unanimity failures
  are surfaced as deadlocks rather than silently resolved.
- Voice sessions store text transcripts, not raw audio. They are readable only by
  the initiating user, and speech never bypasses chat authorization or approval.
- Conflict resolution preserves both original memories and writes a linked
  resolved statement to each affected coworker scope, retaining provenance.
