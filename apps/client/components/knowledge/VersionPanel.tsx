"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import {
  type DocumentDetail,
  type IngestionStage,
  type VersionStatus,
  type VersionSummary,
  errorMessage,
  getDocument,
  getVersionStatus,
  retryVersion,
} from "@/lib/api";
import { fileSize, relativeTime } from "@/lib/format";
import type { Notify } from "@/lib/upload";

const STAGE_LABEL: Record<IngestionStage, string> = {
  parsing: "Reading the file",
  chunking: "Splitting it into passages",
  embedding: "Indexing passages",
  indexing: "Indexing passages",
  done: "Finishing up",
};

interface Props {
  documentId: string;
  refreshToken: string; // changes whenever the parent list sees the document change
  onChanged: () => void | Promise<void>;
  notify: Notify;
}

export function VersionPanel({ documentId, refreshToken, onChanged, notify }: Props) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await getDocument(documentId));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [documentId]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const changed = useCallback(async () => {
    await load();
    await onChanged();
  }, [load, onChanged]);

  if (error) {
    return (
      <p role="alert" className="text-bad">
        {error}
      </p>
    );
  }
  if (!detail) return <p className="text-muted">Loading history</p>;

  const versions = [...detail.versions].sort((a, b) => b.version_number - a.version_number);
  return (
    <ul className="divide-y divide-rule">
      {versions.map((version) => (
        <VersionRow key={version.id} version={version} onChanged={changed} notify={notify} />
      ))}
    </ul>
  );
}

function VersionRow({
  version,
  onChanged,
  notify,
}: {
  version: VersionSummary;
  onChanged: () => void | Promise<void>;
  notify: Notify;
}) {
  const [live, setLive] = useState<VersionStatus | null>(null);
  const [retrying, setRetrying] = useState(false);
  const active = version.status === "pending" || version.status === "processing";

  // While a version is being processed, follow it closely so progress is visible.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const status = await getVersionStatus(version.id);
        if (cancelled) return;
        setLive(status);
        if (status.status !== version.status) void onChanged();
      } catch {
        // transient: the next tick will try again
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [active, version.id, version.status, onChanged]);

  async function retry() {
    setRetrying(true);
    try {
      await retryVersion(version.id);
      notify(`Version ${version.version_number}: processing restarted.`, "success");
      await onChanged();
    } catch (e) {
      notify(errorMessage(e), "error");
    } finally {
      setRetrying(false);
    }
  }

  const progress = live && live.chunks_total > 0 ? live.chunks_embedded / live.chunks_total : null;
  const stage = live?.latest_job?.stage;

  return (
    <li className="grid gap-x-6 gap-y-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[5rem_9rem_1fr]">
      <span className="font-medium">Version {version.version_number}</span>
      <span>
        <StatusBadge status={version.status} />
      </span>
      <div className="min-w-0">
        <p className="text-muted">
          {fileSize(version.file_size)}, uploaded {relativeTime(version.created_at)}
        </p>

        {active && (
          <div className="mt-2 max-w-sm">
            <p>{stage ? STAGE_LABEL[stage] : "Waiting to start"}</p>
            {progress !== null && (
              <div
                role="progressbar"
                aria-label="Indexing progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(progress * 100)}
                className="mt-1 h-1.5 overflow-hidden rounded-full bg-rule"
              >
                <div className="h-full bg-accent transition-[width]" style={{ width: `${progress * 100}%` }} />
              </div>
            )}
          </div>
        )}

        {version.status === "failed" && (
          <div className="mt-2">
            <p className="text-bad">{version.error_message ?? "Processing failed."}</p>
            <button
              onClick={() => void retry()}
              disabled={retrying}
              className="mt-1 underline underline-offset-2 hover:text-accent disabled:opacity-50"
            >
              {retrying ? "Retrying" : "Retry processing"}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}