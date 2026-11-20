"use client";

import type { ConversationSummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

interface Props {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function ConversationList({ conversations, activeId, onSelect, onNew }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-md bg-accent px-3 py-2 font-medium text-accent-ink hover:opacity-90"
        >
          New conversation
        </button>
      </div>
      <nav aria-label="Conversations" className="flex-1 overflow-y-auto pb-3">
        {conversations.length === 0 ? (
          <p className="px-4 py-2 text-muted">Your conversations will appear here.</p>
        ) : (
          <ul>
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <li key={c.id}>
                  <button
                    onClick={() => onSelect(c.id)}
                    aria-current={active ? "true" : undefined}
                    className={`block w-full border-l-2 px-4 py-2 text-left ${
                      active ? "border-accent bg-paper font-medium" : "border-transparent hover:bg-paper"
                    }`}
                  >
                    <span className="block truncate">{c.title}</span>
                    <span className="block text-sm font-normal text-muted">{relativeTime(c.updated_at)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>
    </div>
  );
}