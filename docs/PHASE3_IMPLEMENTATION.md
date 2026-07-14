# Phase 3 implementation

Phase 3 adds the enterprise and ecosystem-maturity layer without forking the
self-hosted product from the hosted product.

## Enterprise identity and governance

- Delegated `security_admin`, `billing_admin`, `developer_admin`, and `auditor`
  roles grant narrowly scoped capabilities alongside owner/admin.
- OIDC authorization-code SSO and signed SAML-broker assertions support JIT
  membership. The SAML broker contract exists because XML signature validation
  belongs at the identity gateway; Deep-Foundry still validates signed state,
  issuer, audience, domain, and broker HMAC before provisioning.
- SCIM 2.0 Users endpoints use independently revocable `scm_` bearer tokens.
- Data-region selection, retention, legal hold, support tier, response targets,
  and uptime targets are workspace policy. A populated workspace cannot silently
  change regions; it must be exported and migrated first.
- Fine-grained ordered rules can allow, deny, or require approval for matching
  resource actions. Tool rules are enforced identically in chat, tasks, and
  workflow runs.

## Audit and compliance

Celery Beat scans organization audit streams for dangerous-action and actor
activity spikes. Security staff can triage deduplicated anomalies. Auditors can
generate access, audit, SOC 2, or full evidence bundles containing membership,
policy, anomaly, and immutable audit data. Every bundle carries a canonical
SHA-256 checksum and excludes credentials.

## Marketplace economy

Publishing produces a security score and findings for bundled code, broad
permissions, and missing dependencies. Installation recursively resolves exact
or latest approved dependencies and rejects cycles. Paid listings create an
order through the configured payment-provider bridge; signed completion webhooks
install the package and create a 15% platform-fee / 85% creator payout ledger.
Payout accounts and transaction history are exposed only to billing roles.

## Portability, workflows, and multimodal artifacts

Coworker bundles contain identity configuration, attached tool names, installed
skill references, and parameterized workflow templates. They omit memory,
provider credentials, integration secrets, and tool configuration. Import
restores available tools, installed skills, and workflows against a new coworker.

The workflow engine supports safe declarative conditions (`equals`,
`not_equals`, `exists`, and `contains`) over run context, with explicit true and
false step indexes; it never evaluates user-supplied code. Presentation, Mermaid
diagram, and timestamped video-analysis outputs are integrity-checked Artifacts
available through the UI and safe built-in tools.

## Operator configuration

Real-money checkout requires `PAYMENTS_CHECKOUT_BASE_URL` and
`PAYMENTS_WEBHOOK_SECRET`. OIDC providers require token and user-info endpoints
in their attribute mapping. Native Desktop Companion builds require Rust/Cargo
and the platform-specific Tauri prerequisites.
