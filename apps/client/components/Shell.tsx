"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceGate } from "@/components/WorkspaceGate";
import { shortId } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

const LINKS = [
  { href: "/ask", label: "Ask" },
  { href: "/knowledge", label: "Knowledge base" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { workspaceId, ready, setWorkspaceId } = useWorkspace();

  if (!ready) return null; // first client render: we don't know the saved workspace yet
  if (!workspaceId) return <WorkspaceGate />;

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <header className="flex h-14 shrink-0 items-center gap-5 border-b border-rule bg-surface px-4 md:sticky md:top-0 md:h-dvh md:w-56 md:flex-col md:items-stretch md:gap-0 md:border-r md:border-b-0 md:px-0 md:py-6">
        <Link href="/ask" className="font-serif text-lg leading-tight md:px-5">
          Enterprise
          <br className="hidden md:block" /> Knowledge
        </Link>

        <nav aria-label="Main" className="flex flex-1 gap-1 md:mt-8 md:flex-none md:flex-col md:gap-0">
          {LINKS.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`border-b-2 px-2 py-1 md:border-b-0 md:border-l-2 md:px-5 md:py-2 ${
                  active ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="text-sm text-muted md:mt-auto md:px-5">
          <p className="hidden md:block">Workspace {shortId(workspaceId)}</p>
          <button onClick={() => setWorkspaceId(null)} className="underline underline-offset-2 hover:text-ink">
            Change workspace
          </button>
        </div>
      </header>

      <main className="h-[calc(100dvh-3.5rem)] min-w-0 flex-1 overflow-y-auto md:h-dvh">{children}</main>
    </div>
  );
}