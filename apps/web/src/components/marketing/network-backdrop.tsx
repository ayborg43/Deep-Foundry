import { cn } from "@/lib/utils";

// Ambient "coworker network" that sits behind the hero — the same constellation
// motif as the auth showcase and logo mark, widened for a landscape hero and
// tinted with the DeepSeek-blue primary so it reads in both themes. Purely
// decorative. Reuses the node-float / line-pulse keyframes (globals.css).
const NODES = [
  { x: 150, y: 150, r: 3 },
  { x: 320, y: 90, r: 2.5 },
  { x: 470, y: 210, r: 3.5 },
  { x: 250, y: 300, r: 2.5 },
  { x: 620, y: 120, r: 2.5 },
  { x: 560, y: 320, r: 3 },
  { x: 760, y: 240, r: 2.5 },
  { x: 900, y: 130, r: 3.5 },
  { x: 1050, y: 250, r: 2.5 },
  { x: 980, y: 380, r: 3 },
  { x: 1120, y: 120, r: 2.5 },
  { x: 700, y: 420, r: 2.5 },
  { x: 400, y: 430, r: 3 },
  { x: 850, y: 460, r: 2.5 },
];

const EDGES: [number, number][] = [
  [0, 1],
  [0, 3],
  [1, 2],
  [2, 4],
  [2, 5],
  [3, 12],
  [4, 6],
  [5, 6],
  [5, 11],
  [6, 7],
  [7, 8],
  [7, 10],
  [8, 9],
  [9, 13],
  [11, 12],
  [11, 13],
];

export function NetworkBackdrop({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 1200 560"
      preserveAspectRatio="xMidYMid slice"
      className={cn("text-primary", className)}
    >
      <g stroke="currentColor" strokeLinecap="round">
        {EDGES.map(([a, b], i) => (
          <line
            key={`${a}-${b}`}
            x1={NODES[a].x}
            y1={NODES[a].y}
            x2={NODES[b].x}
            y2={NODES[b].y}
            strokeWidth="1"
            className="auth-network-line"
            style={{
              animationDelay: `${(i % 7) * 0.7}s`,
              animationDuration: `${6 + (i % 4)}s`,
            }}
          />
        ))}
      </g>
      <g fill="currentColor">
        {NODES.map((node, i) => (
          <circle
            key={i}
            cx={node.x}
            cy={node.y}
            r={node.r}
            className="auth-network-node"
            style={{
              animationDelay: `${(i % 6) * 0.9}s`,
              animationDuration: `${9 + (i % 5) * 1.2}s`,
              transformOrigin: `${node.x}px ${node.y}px`,
            }}
          />
        ))}
      </g>
    </svg>
  );
}
