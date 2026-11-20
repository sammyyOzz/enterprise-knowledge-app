"use client";

import { Fragment, useRef, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { VersionPanel } from "@/components/knowledge/VersionPanel";
import type { DocumentSummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { ACCEPTED_EXTENSIONS, type Notify, uploadFiles } from "@/lib/upload";

interface Props {
  docs: DocumentSummary[];
  workspaceId: string;
  onChanged: () => void | Promise<void>;
  notify: Notify;
}

export function DocumentTable({ docs, workspaceId, onChanged, notify }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-left">
        <caption className="sr-only">Documents in this workspace</caption>
        <thead>
          <tr className="border-b border-rule text-sm text-muted">
            <th scope="col" className="py-2 pr-4 font-medium">Document</th>
            <th scope="col" className="py-2 pr-4 font-medium">Version</th>
            <th scope="col" className="py-2 pr-4 font-medium">Status</th>
            <th scope="col" className="py-2 pr-4 font-medium">Updated</th>
            <th scope="col" className="py-2 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              open={openId === doc.id}
              onToggle={() => setOpenId(openId === doc.id ? null : doc.id)}
              workspaceId={workspaceId}
              onChanged={onChanged}
              notify={notify}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface RowProps {
  doc: DocumentSummary;
  open: boolean;
  onToggle: () => void;
  workspaceId: string;
  onChanged: () => void | Promise<void>;
  notify: Notify;
}

function DocumentRow({ doc, open, onToggle, workspaceId, onChanged, notify }: RowProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function addVersion(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      await uploadFiles(workspaceId, [file], notify, doc.id);
    } finally {
      setUploading(false);
      await onChanged();
    }
  }

  const detailId = `versions-${doc.id}`;

  return (
    <Fragment>
      <tr className="border-b border-rule align-top">
        <th scope="row" className="max-w-[22rem] py-3 pr-4 font-medium">
          <span className="block truncate" title={doc.filename}>
            {doc.filename}
          </span>
        </th>
        <td className="py-3 pr-4">v{doc.current_version}</td>
        <td className="py-3 pr-4">
          <StatusBadge status={doc.status} />
        </td>
        <td className="py-3 pr-4 text-muted">{relativeTime(doc.updated_at)}</td>
        <td className="py-3 text-right">
          <div className="flex flex-wrap justify-end gap-x-4 gap-y-1">
            <button
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="underline underline-offset-2 hover:text-accent disabled:opacity-50"
            >
              {uploading ? "Uploading" : "Upload new version"}
            </button>
            <button
              onClick={onToggle}
              aria-expanded={open}
              aria-controls={detailId}
              className="underline underline-offset-2 hover:text-accent"
            >
              {open ? "Hide history" : "History"}
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="sr-only"
            tabIndex={-1}
            aria-label={`New version of ${doc.filename}`}
            onChange={(e) => {
              void addVersion(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </td>
      </tr>
      {open && (
        <tr id={detailId} className="border-b border-rule">
          <td colSpan={5} className="bg-surface px-4 py-4">
            <VersionPanel
              documentId={doc.id}
              refreshToken={`${doc.updated_at}:${doc.status}`}
              onChanged={onChanged}
              notify={notify}
            />
          </td>
        </tr>
      )}
    </Fragment>
  );
}