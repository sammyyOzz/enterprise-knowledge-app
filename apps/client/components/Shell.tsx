"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/ask", label: "Ask" },
  { href: "/knowledge", label: "Knowledge base" },
];
const PUBLIC_PATHS = ["/login", "/signup"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { status, me, workspaceId, setWorkspaceId, signOut } = useAuth();
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (status === "anonymous" && !isPublic) router.replace("/login");
    if (status === "authenticated" && isPublic) router.replace("/ask");
  }, [status, isPublic, router]);

  if (status === "loading") return null;
  if (isPublic) return status === "anonymous" ? <>{children}</> : null;
  if (status === "anonymous" || !me) return null; // redirecting to /login

  if (!workspaceId) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center px-6">
        <h1 className="font-serif text-[28px] leading-tight">No workspace yet</h1>
        <p className="mt-3 text-muted">
          You&apos;re signed in as {me.user.email}, but you don&apos;t belong to a workspace. Ask an administrator to add
          you to one.
        </p>
        <button onClick={() => void signOut()} className="mt-6 self-start underline underline-offset-2">
          Sign out
        </button>
      </div>
    );
  }

  const multiple = me.workspaces.length > 1;

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

        <div className="flex items-center gap-3 text-sm md:mt-auto md:flex-col md:items-stretch md:gap-1 md:px-5">
          {multiple && (
            <div className="hidden md:block">
              <label htmlFor="workspace" className="text-muted">
                Workspace
              </label>
              <select
                id="workspace"
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-rule bg-paper px-2 py-1"
              >
                {me.workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <p className="hidden truncate text-muted md:block" title={me.user.email}>
            {me.user.full_name ?? me.user.email}
          </p>
          <button
            onClick={() => void signOut()}
            className="text-left text-muted underline underline-offset-2 hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="h-[calc(100dvh-3.5rem)] min-w-0 flex-1 overflow-y-auto md:h-dvh">{children}</main>
    </div>
  );
}