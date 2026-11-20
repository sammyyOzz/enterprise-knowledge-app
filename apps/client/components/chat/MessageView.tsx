"use client";

import { useState } from "react";
import type { Citation } from "@/lib/api";

export type MessageStatus = "done" | "streaming" | "error" | "stopped";

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  refused: boolean;
  status: MessageStatus;
  errorText?: string;
}

const MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

const CHIP =
  "inline-flex h-5 min-w-5 items-center justify-center rounded-sm bg-mark px-1 align-baseline text-[12px] font-medium leading-none text-mark-ink";

/** Turns "[1]" / "[1, 2]" markers in the answer into chips that jump to the matching source. */
function renderWithCitations(text: string, cited: Set<number>, onCite: (n: number) => void) {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    const numbers = match[1].split(/\s*,\s*/).map(Number);
    nodes.push(
      <span key={key++} className="mx-0.5 inline-flex gap-0.5 whitespace-nowrap">
        {numbers.map((n) =>
          cited.has(n) ? (
            <button
              key={n}
              onClick={() => onCite(n)}
              aria-label={`Show source ${n}`}
              className={`${CHIP} hover:opacity-80`}
            >
              {n}
            </button>
          ) : (
            <span key={n} className="text-muted">
              [{n}]
            </span>
          ),
        )}
      </span>,
    );
    last = start + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function scrollToSource(id: string) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
}

export function MessageView({ message, onRetry }: { message: UiMessage; onRetry?: () => void }) {
  const [active, setActive] = useState<number | null>(null);

  if (message.role === "user") {
    return (
      <div className="mt-9 border-t border-rule pt-7 first:mt-0 first:border-t-0 first:pt-0">
        <p className="max-w-[66ch] whitespace-pre-wrap text-[17px] font-medium leading-snug">{message.content}</p>
      </div>
    );
  }

  const streaming = message.status === "streaming";
  const interactive = message.status === "done" && message.citations.length > 0;
  const cited = new Set(message.citations.map((c) => c.index));

  function cite(n: number) {
    setActive(n);
    scrollToSource(`src-${message.id}-${n}`);
  }

  return (
    <div className="mt-4">
      <div className="max-w-[66ch] whitespace-pre-wrap font-serif text-[17px] leading-[1.65]">
        {interactive ? renderWithCitations(message.content, cited, cite) : message.content}
        {streaming && (
          <span aria-hidden className="ml-0.5 inline-block h-[1.05em] w-0.5 translate-y-[0.2em] animate-pulse bg-ink" />
        )}
        {streaming && message.content === "" && <span className="font-sans text-muted">Searching your documents</span>}
      </div>

      {message.status === "done" && message.refused && message.citations.length === 0 && (
        <p className="mt-3 max-w-[66ch] border-l-2 border-muted pl-3 text-sm text-muted">
          No document backs this answer.
        </p>
      )}

      {message.status === "error" && (
        <div role="alert" className="mt-3 max-w-[66ch] border-l-2 border-bad pl-3 text-bad">
          <p>{message.errorText ?? "The answer couldn't be completed."}</p>
          {onRetry && (
            <button onClick={onRetry} className="mt-1 underline underline-offset-2">
              Ask again
            </button>
          )}
        </div>
      )}

      {message.status === "stopped" && (
        <p className="mt-2 text-sm text-muted">
          Stopped.{" "}
          {onRetry && (
            <button onClick={onRetry} className="underline underline-offset-2 hover:text-ink">
              Ask again
            </button>
          )}
        </p>
      )}

      {message.citations.length > 0 && message.status === "done" && (
        <section aria-label="Sources" className="mt-5 max-w-[66ch]">
          <h3 className="text-sm font-medium text-muted">Sources</h3>
          <ol className="mt-2 list-none space-y-2">
            {message.citations.map((c) => (
              <li
                key={c.chunk_id}
                id={`src-${message.id}-${c.index}`}
                className={`-mx-2 grid grid-cols-[1.75rem_1fr] gap-2 rounded-md p-2 ${
                  active === c.index ? "bg-surface ring-1 ring-accent" : ""
                }`}
              >
                <span className={`${CHIP} mt-0.5`}>{c.index}</span>
                <div className="min-w-0">
                  <p className="font-medium">
                    {c.filename}
                    <span className="font-normal text-muted">
                      {c.page_number ? `, page ${c.page_number}` : ""}
                      {c.version_number > 1 ? `, version ${c.version_number}` : ""}
                    </span>
                  </p>
                  {c.heading_path && <p className="text-sm text-muted">{c.heading_path}</p>}
                  <p className="mt-1 text-[15px] leading-relaxed">
                    <span className="box-decoration-clone bg-mark/50 px-0.5">{c.snippet}</span>
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}