# Deep-Foundry — Product context (design)

**Register:** product (design SERVES the task; the tool should disappear into the work).

Deep-Foundry is a self-hostable AI coworker platform — a DeepSeek product. Users
create persistent AI "coworkers", assign them tasks (background) or chat with them
(streaming), attach knowledge/memory/tools, and gate risky actions behind approvals.
Positioned against the best product tools of the category: Linear, Notion, Raycast,
Stripe, claude.ai. The bar is **earned familiarity** — trusted, not surprising.

## Users & scene
Operators and builders working in a focused, authenticated app, often for long
sessions, frequently at night. Dark-first UI (the app ships `dark` on `<html>`).
Density is welcome where it earns its keep (task lists, tables, settings).

## Design language (existing, keep)
- **Color:** DeepSeek blue `#4D6BFE` family as the single accent (primary actions,
  current selection, state). Cool near-neutral surfaces, low chroma. OKLCH tokens
  in `src/app/globals.css`, shadcn-compatible so components reskin without markup.
  Strategy: **Restrained** (accent ≤ ~10% of surface).
- **Type:** Geist Sans for all UI (one family, tuned weights). Geist Mono for code.
  No serif in product chrome.
- **Radius:** `--radius: 0.75rem` base, scaled tokens.
- **Motion:** 150–250ms, conveys state only. Respect `prefers-reduced-motion`.

## Non-negotiables
- One accent, used for meaning not decoration; heavy saturation never on inactive
  states.
- Every interactive element ships default / hover / focus-visible / active /
  disabled. Consistent affordance vocabulary across every screen.
- No display/serif fonts in labels, buttons, data. No invented affordances for
  standard tasks. No decorative motion.
