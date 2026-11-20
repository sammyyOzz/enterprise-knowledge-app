"use client";

import { useState } from "react";
import { UUID_RE, useWorkspace } from "@/lib/workspace";

export function WorkspaceGate() {
  const { setWorkspaceId } = useWorkspace();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!UUID_RE.test(trimmed)) {
      setError("That doesn't look like a workspace ID. It should be a UUID, like 3f2b8c1e-....");
      return;
    }
    setWorkspaceId(trimmed);
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center px-6 py-12">
      <h1 className="font-serif text-[28px] leading-tight">Choose a workspace</h1>
      <p className="mt-3 max-w-[58ch] text-muted">
        Documents and questions belong to one workspace. Paste the workspace ID printed by the seed
        script. If you haven&apos;t run it yet:
      </p>
      <pre className="mt-3 overflow-x-auto rounded-md border border-rule bg-surface px-3 py-2 font-mono text-sm">
        docker compose exec api python -m api.scripts.seed
      </pre>

      <form onSubmit={submit} className="mt-8">
        <label htmlFor="workspace-id" className="font-medium">
          Workspace ID
        </label>
        <input
          id="workspace-id"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(null);
          }}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "workspace-error" : undefined}
          className="mt-1 block w-full rounded-md border border-rule bg-surface px-3 py-2 font-mono text-sm"
        />
        {error && (
          <p id="workspace-error" role="alert" className="mt-2 text-bad">
            {error}
          </p>
        )}
        <button
          type="submit"
          className="mt-4 rounded-md bg-accent px-4 py-2 font-medium text-accent-ink hover:opacity-90"
        >
          Use this workspace
        </button>
      </form>
    </div>
  );
}