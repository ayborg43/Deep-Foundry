# Deep-Foundry — Product context (design)

**Register:** product (design SERVES the task; the tool should disappear into the work).

Deep-Foundry is a self-hostable AI coworker platform — a DeepSeek product. Users
create persistent AI "coworkers", assign them tasks (background) or chat with them
(streaming), attach knowledge/memory/tools, and gate risky actions behind approvals.
Positioned against the best product tools of the category: Linear, Notion, Raycast,
Stripe, claude.ai. The bar is **earned familiarity** — trusted, not surprising.

## Users & scene
Operators and builders working in a focused, authenticated app, often for long
sessions. The warm light theme is the default and dark mode is fully paired.
Density is welcome where it earns its keep (task lists, tables, settings).

## Design language (existing, keep)
- **Color:** Foundry orange `#C2410C` is the single accent for selection and
  emphasis. Warm paper, white surfaces, and ink form the light theme; dark mode
  uses warm near-black surfaces with a lifted orange. Tokens remain shadcn-compatible.
  Strategy: **Restrained** (accent ≤ ~10% of surface).
- **Type:** Hanken Grotesk for UI and headings. JetBrains Mono for code and data.
  No serif in product chrome.
- **Radius:** `--radius: 0.6875rem` base, scaled tokens.
- **Motion:** 150–250ms, conveys state only. Respect `prefers-reduced-motion`.

## Non-negotiables
- One accent, used for meaning not decoration; heavy saturation never on inactive
  states.
- Every interactive element ships default / hover / focus-visible / active /
  disabled. Consistent affordance vocabulary across every screen.
- No display/serif fonts in labels, buttons, data. No invented affordances for
  standard tasks. No decorative motion.
