# Phase 2 implementation

Phase 2 is implemented across five user-visible paths:

- **Organizations:** workspace roles, invitations, human teams, organization
  approval floors, shared coworker ownership, projects, API tokens, and plans.
- **Agent Teams and automation:** versioned manager/delegate, sequential, and
  parallel/merge teams; durable task routing; manual, cron, and signed-event
  workflow triggers; approval checkpoints; resumable run history; Celery Beat.
- **Marketplace and SDK:** public/private listings, automated declarative-package
  review, install, fork, ratings, reusable skills, and first-party Developer,
  Marketing, and Research packs. `packages/agentarium-sdk` provides validate,
  test, and publish commands using scoped `agt_` tokens.
- **Connected operation:** email/calendar/Slack/Discord/GitHub/webhook connection
  records, HMAC webhook ingress, browser speech input/output, subscriptions, and
  OpenAI-compatible self-hosted DeepSeek endpoints.
- **Desktop Companion:** a Tauri application whose filesystem and folder watcher
  are constrained to canonical granted directories, whose terminal proposals use
  one-time approval tokens, and whose clipboard/browser commands remain local.

## Acceptance path

1. Start the stack and sign in to a workspace.
2. Open **Marketplace**, install **Developer Team**, then open **Agent teams**.
3. Run an objective and inspect its delegated tasks from **Tasks**.
4. Open **Workflows**, run the installed weekly workflow, and approve its human
   checkpoint. Celery Beat evaluates its Monday schedule.
5. Create a publish-scoped token at
   `POST /api/v1/workspaces/{workspace_id}/api-tokens`, then use the SDK's
   `publish` command. Safe declarative skills are approved automatically;
   dangerous tools and bundled code remain pending.

## Verification

The maintained checks are Django's full test suite, migration drift detection,
the Next.js production build, and the SDK example contract test. Desktop builds
also require Rust and the native Tauri prerequisites for the target platform.
