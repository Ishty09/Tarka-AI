export interface ExportRow {
  id: string;
  status: "pending" | "processing" | "ready" | "failed" | "expired";
  requested_at: string;
  ready_at: string | null;
  expires_at: string | null;
  byte_size: number | null;
  error_message: string | null;
}

const STATUS_LABEL: Record<ExportRow["status"], string> = {
  pending: "Queued",
  processing: "Building",
  ready: "Emailed",
  failed: "Failed",
  expired: "Expired",
};

const STATUS_TONE: Record<ExportRow["status"], string> = {
  pending: "bg-muted text-muted-foreground",
  processing: "bg-blue-100 text-blue-900",
  ready: "bg-emerald-100 text-emerald-900",
  failed: "bg-destructive/10 text-destructive",
  expired: "bg-muted text-muted-foreground",
};

function formatBytes(n: number | null): string {
  if (n === null || n === 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExportHistory({ rows }: { rows: ExportRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No exports yet. The first one you request will show up here.
      </p>
    );
  }

  return (
    <ul className="flex flex-col divide-y rounded-md border border-input text-sm">
      {rows.map((row) => {
        const requested = new Date(row.requested_at).toLocaleString();
        const expires = row.expires_at ? new Date(row.expires_at) : null;
        const expired = expires ? expires.getTime() < Date.now() : false;
        const effectiveStatus: ExportRow["status"] =
          expired && row.status === "ready" ? "expired" : row.status;
        return (
          <li key={row.id} className="flex items-center justify-between gap-3 p-3">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">{requested}</span>
              {row.status === "ready" && expires ? (
                <span className="text-xs text-muted-foreground">
                  Link {expired ? "expired" : "expires"} {expires.toLocaleDateString()}
                </span>
              ) : null}
              {row.status === "failed" && row.error_message ? (
                <span className="text-xs text-destructive">
                  {row.error_message}
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>{formatBytes(row.byte_size)}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${STATUS_TONE[effectiveStatus]}`}
              >
                {STATUS_LABEL[effectiveStatus]}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
