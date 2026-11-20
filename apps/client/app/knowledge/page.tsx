"use client";

import { DocumentTable } from "@/components/knowledge/DocumentTable";
import { UploadZone } from "@/components/knowledge/UploadZone";
import { Notices, useNotices } from "@/components/Notices";
import { useDocuments } from "@/lib/useDocuments";
import { useRequiredWorkspace } from "@/lib/workspace";

export default function KnowledgePage() {
  const workspaceId = useRequiredWorkspace();
  const { docs, error, refresh } = useDocuments(workspaceId);
  const { notices, notify, dismiss } = useNotices();

  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-8 md:px-10 md:py-12">
      <h1 className="font-serif text-[28px] leading-tight">Knowledge base</h1>
      <p className="mt-2 max-w-[62ch] text-muted">
        Add documents here. Once a document shows Ready, you can ask questions about it.
      </p>

      <div className="mt-8">
        <UploadZone workspaceId={workspaceId} onUploaded={refresh} notify={notify} />
      </div>

      <section className="mt-10" aria-label="Documents">
        {error && (
          <div role="alert" className="mb-4 border-l-2 border-bad pl-3 text-bad">
            <p>{error}</p>
            <button onClick={() => void refresh()} className="mt-1 underline underline-offset-2">
              Try again
            </button>
          </div>
        )}
        {docs === null && !error && <p className="text-muted">Loading documents</p>}
        {docs !== null && docs.length === 0 && (
          <p className="text-muted">No documents yet. Drop a file above to add your first one.</p>
        )}
        {docs !== null && docs.length > 0 && (
          <DocumentTable docs={docs} workspaceId={workspaceId} onChanged={refresh} notify={notify} />
        )}
      </section>

      <Notices notices={notices} onDismiss={dismiss} />
    </div>
  );
}