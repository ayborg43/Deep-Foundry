## CONTRIBUTING.md

# Contributing to Agentarium

> Operationalizes `SOUL.md` [Section 20 (Development Rules)](SOUL.md#20-development-rules) and principle 6, "Community first" ([Section 3](SOUL.md#3-product-principles)). If anything here conflicts with `SOUL.md`, `SOUL.md` governs — open an issue proposing a revision to this document instead of quietly diverging from it.

## 1. Before You Start

Agentarium is documentation-first. Read `SOUL.md` in full before proposing any feature — it is the constitution every contribution is measured against. If your idea contradicts a principle or concept in `SOUL.md`, the correct first PR is a proposed revision to `SOUL.md` itself, discussed and merged before any implementation PR builds on it.

For structural changes, also check: `ARCHITECTURE.md` (service boundaries), `DATABASE.md` (schema), `API.md` (contracts), `SECURITY.md` (permission/risk model), `UI_GUIDELINES.md` (client-facing conventions).

## 2. Repository Structure (target — evolves alongside `ARCHITECTURE.md`)

```
/apps
  /web              (Next.js — primary client)
  /desktop          (Tauri — Desktop Companion)
/services
  /app              (the modular monolith — one Django project, one image, ARCHITECTURE.md §3.1/ADR-006)
    /core           (Django apps: auth, workspace, coworkers, projects, marketplace, billing, admin/audit)
    /ai             (FastAPI sub-app + modules: model_router, memory, knowledge, task_engine,
                     workflow_engine — mounted at /ai/* in the ASGI app; imported directly,
                     not called over HTTP, by /worker below)
    /worker         (Celery app + worker entrypoint — same image as /app, different command;
                     imports /core and /ai directly, no network hop)
/packages
  /sdk              (Developer SDK — TypeScript + Python)
  /ui               (shared design system components, consumed by /apps/web and /apps/desktop)
/docs               (this document set)
/infra              (docker-compose.yml — deployed via Dokploy for self-hosted, ARCHITECTURE.md §8.1/ADR-008; k8s manifests for cloud; CI config)
```

## 3. Development Rules (binding, from `SOUL.md` §20)

1. **Every feature requires documentation.** A PR that adds a feature without a corresponding update to the relevant doc (`SOUL.md` if conceptual, `ARCHITECTURE.md`/`DATABASE.md`/`API.md` if structural, `UI_GUIDELINES.md` if user-facing) will be requested to add it before merge, not after.
2. **Every API documented.** New or changed endpoints require an `API.md` update in the same PR.
3. **Every database change documented.** Schema migrations require a `DATABASE.md` update in the same PR — the migration file and the doc entry are reviewed together.
4. **Every architecture decision documented.** Non-trivial decisions get an ADR entry in `ARCHITECTURE.md` §11 — what was decided, why, and what was rejected.
5. **Every module tested.** Coverage bar scales with risk: permission/security-critical code paths (anything touching `SECURITY.md` §3–5) require the highest bar and must include adversarial test cases, not just happy-path.
6. **Everything modular, extensible, versioned, forkable.** See `SOUL.md` §3, principles 3–5. A PR that hardcodes a capability into a single coworker/feature instead of expressing it as a Skill/Tool/Workflow will be asked to restructure before merge.
7. **No silent contradiction of `SOUL.md`.** Reviewers are expected to reject (not quietly approve) any change that contradicts a stated principle without an accompanying `SOUL.md` revision proposal.

## 4. Contribution Types & Process

### 4.1 Core platform code (services, apps, packages)
1. Open an issue describing the problem/feature before a large PR — small fixes can skip straight to a PR.
2. Fork, branch, implement, include tests and doc updates per §3 above.
3. PR description must state: what changed, why, which `SOUL.md`/architecture doc sections it touches, and how it was tested.
4. At least one maintainer review required; security-relevant PRs (anything touching permission evaluation, sandboxing, secrets, or the approval system) require a maintainer with security review authority specifically.

### 4.2 Skills, Tools, and Capability Packs (Marketplace content)
- Authored via the Developer SDK (`SOUL.md` §5.12), not by forking core platform code.
- Must declare every Tool used and its risk classification accurately in the manifest — misdeclaration is treated as a security issue, not a bug, per `SECURITY.md` §7.
- Submitted through the marketplace publishing flow (`API.md` §8, §13), subject to the automated + human review pipeline in `SECURITY.md` §7 — this review is separate from, and does not require, core repository maintainer involvement.

### 4.3 Documentation-only contributions
Always welcome, lighter review bar than code — but changes to `SOUL.md` itself require the explicit-revision process (§5 below), since it's the one document every other artifact depends on.

## 5. Proposing a `SOUL.md` Revision

Because `SOUL.md` is binding on all future work, changing it is not a normal doc PR:

1. Open an issue tagged `soul-revision` stating the principle/concept being changed and why the current version is wrong or insufficient — not just "I want to add X," but "X cannot be built without changing principle Y, here's why Y should change."
2. Discussion period (community + maintainers) before a PR is opened.
3. The PR must update `SOUL.md` **and** identify every downstream document/feature that the revision affects, even if those follow-up updates land in separate PRs.
4. Requires maintainer consensus (not a single-reviewer merge) given the blast radius.

## 6. Code Style & Conventions

- **Core modules (Django/DRF, `services/app/core`):** standard Django app layout, DRF viewsets/serializers per resource, `black`/`ruff` formatting, type hints required on new code.
- **AI modules (FastAPI, `services/app/ai`, mounted at `/ai/*`):** async-first, Pydantic models for every request/response schema (mirroring `API.md` contracts, not diverging from them), `black`/`ruff` formatting. Never import Core internals directly — go through the interface in `API.md` §12, since that's the boundary a future service split would cut along.
- **Frontend (Next.js/TypeScript):** strict TypeScript, shadcn/ui components before custom ones, Tailwind utility classes over ad hoc CSS, ESLint + Prettier enforced in CI.
- **Commit messages:** conventional-commits style (`feat:`, `fix:`, `docs:`, `refactor:`) to keep changelog generation (relevant to the Marketplace/API deprecation policy in `API.md` §15) mechanical rather than manual.

## 7. Testing Expectations

- Unit tests for all new business logic.
- Integration tests for any new API endpoint (`API.md` contract compliance).
- Every pull request runs migration-drift detection, the full Django suite, frontend lint/build, and both production container builds in `.github/workflows/ci.yml`.
- For anything touching the permission/approval system: explicit test cases proving a `dangerous` tool call cannot execute without an approval record, and that org policy floors cannot be lowered by a coworker-level config — these are the platform's core trust guarantees and regressions here are treated as release-blocking.
- For Skills/Tools submitted to the Marketplace: the SDK's local validation harness (`API.md` §13) must pass before submission; it's the first automated gate in the review pipeline (`SECURITY.md` §7).

## 8. Security Disclosure

Do not open a public issue for a suspected security vulnerability. Follow the responsible-disclosure process referenced in `SECURITY.md` §10 (published alongside the repository) — a documented private contact channel with a stated response SLA.

## 9. Governance

MVP-phase governance is maintainer-led (the core team owns merge authority and `SOUL.md` revision consensus). As the community and Marketplace mature (`ROADMAP.md` Phase 2/3), governance evolves toward a documented RFC process with broader community voice — this evolution will itself be documented here when it happens, per the "everything documented" rule this whole file exists to enforce.

## 10. Code of Conduct

Contributors are expected to engage in good faith, assume good intent, and prioritize the project's principles (`SOUL.md` §3) — especially "community first" and "privacy first" — over individual preference in disputes. A full Code of Conduct document is adopted alongside the first public contribution window (tracked as a Phase 1 exit item, not deferred indefinitely).
