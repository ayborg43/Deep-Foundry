import { BrainIcon, ShieldCheckIcon, UsersRoundIcon } from "lucide-react";

import { LogoMark } from "@/components/logo";

// Nodes for the ambient "coworker network" — an enlarged, populated take on
// the constellation in the wordmark (one hub, many linked coworkers). Fixed
// coordinates in a 400x600 viewBox; each node/line drifts and pulses on its
// own timing (see the `node-float` / `line-pulse` keyframes in globals.css)
// so the panel reads as alive rather than a single uniform loop.
type Node = { id: number; x: number; y: number; r?: number; hub?: boolean };

const NODES: Node[] = [
  { id: 0, x: 300, y: 470, r: 7, hub: true },
  { id: 1, x: 178, y: 372 },
  { id: 2, x: 344, y: 314 },
  { id: 3, x: 222, y: 526 },
  { id: 4, x: 118, y: 462 },
  { id: 5, x: 366, y: 436 },
  { id: 6, x: 262, y: 198 },
  { id: 7, x: 78, y: 258 },
  { id: 8, x: 382, y: 176 },
  { id: 9, x: 138, y: 138 },
  { id: 10, x: 302, y: 88 },
  { id: 11, x: 58, y: 398 },
  { id: 12, x: 198, y: 562 },
  { id: 13, x: 344, y: 566 },
];

const EDGES: [number, number][] = [
  [0, 1],
  [0, 3],
  [0, 4],
  [0, 5],
  [0, 13],
  [1, 7],
  [1, 11],
  [2, 5],
  [2, 6],
  [2, 8],
  [6, 9],
  [6, 10],
  [9, 7],
  [4, 11],
  [3, 12],
];

const FEATURES = [
  { icon: BrainIcon, label: "Remembers context across every session" },
  { icon: UsersRoundIcon, label: "Coordinates as multi-agent teams" },
  { icon: ShieldCheckIcon, label: "Asks before it acts on anything risky" },
];

// The brand "front door" panel shared by /login and /signup. Deliberately
// drenched dark + Foundry orange regardless of the site's light/dark
// preference — the showcase is a fixed brand moment, not themed chrome.
export function AuthShowcase() {
  return (
    <div className="relative hidden overflow-hidden bg-[oklch(0.16_0.02_264)] lg:block">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-24 top-[-10%] size-[32rem] rounded-full opacity-40 blur-3xl"
        style={{ background: "oklch(0.585 0.22 269)" }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-15%] right-[-10%] size-[28rem] rounded-full opacity-30 blur-3xl"
        style={{ background: "oklch(0.66 0.19 269)" }}
      />

      <svg
        aria-hidden="true"
        viewBox="0 0 400 600"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 size-full"
      >
        <g strokeLinecap="round">
          {EDGES.map(([a, b], i) => {
            const from = NODES[a];
            const to = NODES[b];
            return (
              <line
                key={`${a}-${b}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="oklch(0.72 0.14 269)"
                strokeWidth="1"
                className="auth-network-line"
                style={{
                  animationDelay: `${(i % 7) * 0.6}s`,
                  animationDuration: `${5 + (i % 4)}s`,
                }}
              />
            );
          })}
        </g>
        <g>
          {NODES.map((node, i) => (
            <circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={node.r ?? 3.5}
              fill={node.hub ? "oklch(0.99 0.01 262)" : "oklch(0.78 0.1 269)"}
              className="auth-network-node"
              style={{
                animationDelay: `${(i % 6) * 0.9}s`,
                animationDuration: `${9 + (i % 5) * 1.3}s`,
                transformOrigin: `${node.x}px ${node.y}px`,
              }}
            />
          ))}
        </g>
      </svg>

      <div className="relative flex h-full flex-col justify-between p-10 xl:p-14">
        {/* Duplicate of the real, accessible Home link in the form column —
         * hidden from AT so it isn't announced twice; a div rather than a
         * Link so it's not a focusable-but-redundant stop either. */}
        <div aria-hidden="true" className="flex items-center gap-2.5">
          <LogoMark className="size-8" />
          <span className="text-[0.9375rem] font-semibold tracking-tight text-white">
            Deep-Foundry
          </span>
        </div>

        <div className="max-w-md">
          <p className="text-balance font-heading text-[clamp(1.75rem,2.6vw+1rem,2.75rem)] font-medium leading-[1.1] tracking-[-0.02em] text-white">
            Coworkers that remember, act, and check in before they leap.
          </p>
          <ul className="mt-8 flex flex-col gap-3">
            {FEATURES.map(({ icon: Icon, label }) => (
              <li
                key={label}
                className="flex items-center gap-2.5 text-sm text-white/70"
              >
                <Icon aria-hidden="true" className="size-4 shrink-0 text-[oklch(0.78_0.1_269)]" />
                {label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
