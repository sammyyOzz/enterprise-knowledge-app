"use client";

import { useCallback, useRef, useState } from "react";

export type NoticeTone = "info" | "success" | "error";
export interface Notice {
  id: number;
  tone: NoticeTone;
  text: string;
}

export function useNotices() {
  const [notices, setNotices] = useState<Notice[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setNotices((current) => current.filter((n) => n.id !== id));
  }, []);

  const notify = useCallback(
    (text: string, tone: NoticeTone = "info") => {
      const id = ++counter.current;
      setNotices((current) => [...current.slice(-3), { id, tone, text }]);
      setTimeout(() => dismiss(id), tone === "error" ? 10_000 : 5_000);
    },
    [dismiss],
  );

  return { notices, notify, dismiss };
}

const RULE: Record<NoticeTone, string> = {
  info: "border-muted",
  success: "border-ok",
  error: "border-bad",
};

export function Notices({ notices, onDismiss }: { notices: Notice[]; onDismiss: (id: number) => void }) {
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-20 flex flex-col items-end gap-2">
      {notices.map((notice) => (
        <div
          key={notice.id}
          role={notice.tone === "error" ? "alert" : "status"}
          className={`pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-md border border-rule border-l-[3px] bg-surface px-3 py-2 shadow-sm ${RULE[notice.tone]}`}
        >
          <p className="flex-1 break-words">{notice.text}</p>
          <button
            onClick={() => onDismiss(notice.id)}
            aria-label="Dismiss message"
            className="rounded px-1 text-muted hover:text-ink"
          >
            Close
          </button>
        </div>
      ))}
    </div>
  );
}