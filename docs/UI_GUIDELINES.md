## UI_GUIDELINES.md

# Deep-Foundry — UI/UX Guidelines

> Downstream of `SOUL.md` [Section 1.6 (Design Principles)](SOUL.md#16-design-principles) and the interaction-bearing modules in [Section 5](SOUL.md#5-product-modules) (Chat, Coworkers, Voice, Desktop App). Stack per `SOUL.md` §18: Next.js, TypeScript, Tailwind CSS, shadcn/ui.

## 1. Design Philosophy

Deep-Foundry's interface has to hold two things in tension that most AI products don't: it must feel as immediate and conversational as a chat app, while making persistent, stateful, permissioned entities (coworkers) legible in a way a disposable chat thread never has to be. The UI mantra: **a chat window is a view into a coworker, not the coworker itself.** Every screen should reinforce that the coworker exists before, during, and after any single conversation.

Guiding principles inherited from `SOUL.md` §1.6, applied concretely:

- **Progressive disclosure:** the first screen after signup is one coworker (the Assistant, `SOUL.md` §4.1) ready to chat — not a dashboard, not a team-builder, not a settings wizard. Multi-agent teams, skill marketplace, and workflow automation are one or two navigations away, never blocking the first message.
- **Reversibility over restriction:** favor undo/versioning affordances (visible on coworker config changes, memory edits, workflow templates) over hard confirmation dialogs, except at genuine approval gates.
- **Explicit over implicit:** a coworker's model, permissions, and attached knowledge are always one click from the chat view — never buried in a settings page the user has to go hunting for.

## 2. Information Architecture

```
Workspace (top-level switcher, like a Slack workspace switcher)
 ├─ Home / Inbox        (notifications, pending approvals across all coworkers)
 ├─ Chat                (conversation list, primary daily-use surface)
 ├─ Coworkers           (roster view — every coworker as a card: avatar, role, status)
 ├─ Agent Teams         (V2 — saved team configurations)
 ├─ Projects            (goal-scoped containers)
 ├─ Workflows           (V2 — automation library + run history)
 ├─ Marketplace         (V2 — browse/install skills, packs, workflows)
 ├─ Knowledge           (knowledge base management, cross-coworker)
 └─ Settings
      ├─ Workspace (members, billing, policy floors)
      ├─ Provider Credentials
      └─ Personal (theme, notifications)
```

The **Coworkers roster** is the single most important IA decision: it is the page that makes "these are persistent employees, not chat sessions" legible at a glance. Each coworker card shows: avatar, name, role, current status (idle/working/needs your approval), and a one-line "what I'm doing" if actively executing a background task.

## 3. Core Interaction Patterns

### 3.1 Chat with a Coworker
- Streaming token-by-token response rendering (never a spinner-then-dump).
- **Tool calls render inline, not hidden behind a "thinking" collapse by default** — a coworker calling `web_search` or `read_file` shows as a distinct, labeled inline card in the message stream, expandable for full input/output. Transparency here is a trust mechanic (`SOUL.md` §15.2), not a debugging feature — hide it behind a toggle for power users who want a cleaner view, but default to visible.
- Approval prompts render as an interrupt in the message stream itself — a distinct card (not a modal that steals focus from reading context) showing exactly what action is being requested, its risk classification, and Approve/Deny buttons, with the conversation visibly paused until resolved.
- @mention syntax to bring a second coworker into a conversation (V2), rendered with a clear visual distinction between which coworker said what (consistent avatar + name label per message, not just an alternating left/right bubble convention that stops working past two participants).

### 3.2 Coworker Creation & Configuration
- Creation flow: name → role description (with AI-assisted drafting help, since "write your coworker's job description" is a blank-page problem for many users) → model selection → starter skill/tool suggestions based on the role description → permission profile (defaulted sensibly per risk, editable) → done, chatting immediately.
- Configuration is a persistent side panel or dedicated settings view, not a one-time wizard you can't return to — attaching a new skill or knowledge base to an existing coworker should feel as easy as the initial creation flow.
- Every configuration change creates a version (`DATABASE.md` §2.2); the UI surfaces a lightweight version history with diff and one-click rollback, not just a changelog log.

### 3.3 Approval Queue
- A dedicated, cross-coworker inbox (Home/Inbox in the IA) listing every pending approval request workspace-wide, sortable by coworker/urgency/age — a user should never have to remember which of ten coworkers is blocked waiting on them.
- Each approval item shows the requesting coworker, the exact action, the risk classification, and enough context (the task/workflow it's part of) to decide without switching screens, with a link out to full context if needed.

### 3.4 Marketplace Browsing & Install
- Listing cards show: name, publisher (with verified badge if applicable), rating, install count, pricing, and — critically — a **permission summary** ("requests: send_email [dangerous], web_search [safe]") visible on the card itself, not just after clicking in, so risk is scannable while browsing.
- Install flow surfaces the full consent screen (per `API.md` §8) before the install call fires — explicit, itemized, never a single "Install" button that silently grants everything.

### 3.5 Workflow Builder (V2/V3)
- MVP-adjacent (V2) ships a structured form-based step editor (add step → choose coworker/tool/checkpoint → configure); the visual drag-and-drop canvas builder is a V3 enhancement layered on the same underlying workflow definition schema (`DATABASE.md` §2.6), not a separate system.

### 3.6 Desktop Companion
- Every local capability grant (folder access, terminal, clipboard) is requested through an OS-native permission-style dialog, one capability at a time, with a persistent "what does my Companion have access to" settings page listing every active grant and a one-click revoke per item — mirroring the transparency bar set for cloud tool calls.

## 4. Visual System

- **Component library:** shadcn/ui on Tailwind — chosen for full ownership of component source (no black-box dependency, consistent with the project's open-source-first principle) and straightforward theming.
- **Theming:** light and dark mode as first-class, not an afterthought; respects OS-level `prefers-color-scheme` by default with a manual override in Settings.
- **Coworker identity:** every coworker has a persistent avatar (illustrated/generated, not a generic bot icon) and a consistent accent color used in chat bubbles, roster cards, and notifications — reinforces individual identity across every surface it appears on.
- **Status language:** a small, consistent vocabulary of status states (Idle, Working, Needs Approval, Blocked, Error) with consistent color coding across every module (roster, task lists, workflow runs) — a user should learn the color/icon meaning once and have it hold everywhere.
- **Motion:** streaming text, tool-call card expand/collapse, and approval-interrupt entrances use restrained, purposeful motion (per the general principle that AI product motion should indicate *state change*, not decorate) — no motion for motion's sake, but state transitions (idle → working, pending → approved) should never feel like a hard cut.

## 5. Accessibility

- WCAG 2.1 AA as the baseline bar for all first-party surfaces.
- Full keyboard navigability for chat (send, regenerate, approve/deny) and the approval queue specifically — approvals are often time-sensitive and must not require a mouse.
- Screen-reader labeling for tool-call cards and approval prompts is treated as functionally required, not cosmetic — a screen-reader user must be able to understand *what a coworker is about to do* with the same fidelity as a sighted user, given the trust stakes involved.
- The MVP Chat implementation exposes the message stream as a polite live log, labels composer and icon-only controls, and reports tool-call expansion state with `aria-expanded`/`aria-controls`. Inline approvals are named regions with action-specific button labels. The Approval Queue uses semantic headings/articles, announces loading and errors, and makes overflowing argument payloads keyboard-focusable.
- Color is never the sole signal for status (Idle/Working/Needs Approval/Error) — always paired with an icon and text label.

## 6. Responsive & Multi-Surface Behavior

- Web app is responsive down to tablet width as MVP scope; a dedicated mobile-optimized layout (not just a squeezed desktop layout) for the Chat and Approval Queue surfaces specifically is a V2 priority, since those two are the most plausible "I'm away from my desk and need to respond" use cases.
- Desktop Companion shares the same design system/component source as the web app (via a shared package in the monorepo) so the native app never visually drifts from the web experience.

## 7. Content & Voice Guidelines

- Coworker-authored text (chat responses, task summaries) is the coworker's own voice per its configured persona — but **platform chrome** (buttons, error messages, empty states, approval prompts) speaks in one consistent, neutral, human product voice, clearly distinct from any coworker's voice, so users never confuse "the product telling you something" with "a coworker telling you something."
- Error messages name what happened and what to do next, never a bare error code alone in the primary UI (codes are available in details/logs for support purposes, per `API.md` §1 error envelope).
- Empty states (no coworkers yet, no marketplace installs yet, empty approval queue) are treated as onboarding opportunities, each with one clear next action — never a bare "nothing here."

## 8. What Not to Do

- Do not hide tool-call activity behind an unexpandable "thinking" spinner — this directly undermines the transparency principle the whole permission system depends on for user trust.
- Do not let a coworker's chat identity (name/avatar/persona) bleed into platform chrome — a user must always be able to tell "is this the product talking or my coworker talking."
- Do not implement approval prompts as blocking modals that require dismissing before reading surrounding context — they should coexist with context, not obscure it.
- Do not ship a marketplace install flow that buries permission requests behind a secondary "advanced" or "details" click — the itemized consent screen is the primary flow, not an opt-in detour.
