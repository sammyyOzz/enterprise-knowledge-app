"use client";

import { useState } from "react";
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_BYTES, type Notify, uploadFiles } from "@/lib/upload";

interface Props {
  workspaceId: string;
  onUploaded: () => void | Promise<void>;
  notify: Notify;
}

export function UploadZone({ workspaceId, onUploaded, notify }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function handle(files: File[]) {
    if (files.length === 0 || uploading) return;
    setUploading(true);
    try {
      await uploadFiles(workspaceId, files, notify);
    } finally {
      setUploading(false);
      await onUploaded();
    }
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void handle(Array.from(e.dataTransfer.files));
      }}
      className={`flex cursor-pointer flex-col items-start gap-1 rounded-lg border border-dashed px-6 py-8 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent ${
        dragging ? "border-accent bg-surface" : "border-muted"
      }`}
    >
      <input
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(",")}
        disabled={uploading}
        className="sr-only"
        onChange={(e) => {
          void handle(Array.from(e.target.files ?? []));
          e.target.value = ""; // allow picking the same file again
        }}
      />
      <span className="font-serif text-xl">
        {uploading ? "Uploading" : dragging ? "Drop to upload" : "Drop files here, or choose them"}
      </span>
      <span className="text-muted">
        PDF, Word, text, Markdown and CSV files, up to {MAX_UPLOAD_BYTES / (1024 * 1024)} MB each.
      </span>
    </label>
  );
}