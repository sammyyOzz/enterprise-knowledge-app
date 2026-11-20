import type { ProcessingStatus } from "@/lib/api";

const LABEL: Record<ProcessingStatus, string> = {
  pending: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

const DOT: Record<ProcessingStatus, string> = {
  pending: "bg-muted",
  processing: "bg-warn animate-pulse",
  ready: "bg-ok",
  failed: "bg-bad",
};

// Colour is never the only signal: the status is always spelled out.
export function StatusBadge({ status }: { status: ProcessingStatus | null }) {
  if (!status) return <span className="text-muted">Unknown</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className={`size-2 rounded-full ${DOT[status]}`} />
      {LABEL[status]}
    </span>
  );
}