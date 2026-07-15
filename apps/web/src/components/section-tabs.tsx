"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Sub-navigation for screens that were previously separate top-level rail
// items. Collapsing them into one section each (with these tabs) is what let
// the sidebar shrink from ~22 entries to 8. Rendered once by AppShell based on
// the active route, so individual page files don't each carry their own tabs.
type Section = { items: { href: string; label: string }[] };

const SECTIONS: Section[] = [
  { items: [
    { href: "/coworkers", label: "Coworkers" },
    { href: "/agent-teams", label: "Teams" },
  ] },
  { items: [
    { href: "/tasks", label: "Tasks" },
    { href: "/approvals", label: "Approvals" },
  ] },
  { items: [
    { href: "/knowledge", label: "Knowledge" },
    { href: "/memory", label: "Memory" },
    { href: "/artifacts", label: "Artifacts" },
  ] },
];

function matches(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SectionTabs() {
  const pathname = usePathname();
  const section = SECTIONS.find((s) => s.items.some((item) => matches(pathname, item.href)));
  if (!section) return null;

  return (
    <div className="border-b border-border/70 bg-background/60 px-4">
      <nav aria-label="Section navigation" className="-mb-px flex gap-1 overflow-x-auto">
        {section.items.map((item) => {
          const active = matches(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "border-primary font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
