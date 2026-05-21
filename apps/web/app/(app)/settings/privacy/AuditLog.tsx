// Audit log viewer for /settings/privacy (CLAUDE.md §12.3, §27 step 59).
//
// Reads rows the user is allowed to see via the audit_log_self_select RLS
// policy (companion migration). The page-level server component fetches
// the data and passes it in; this component is presentation-only.

export interface AuditRow {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

// Friendly labels for the action verbs we currently write. New audit
// actions get a fallback that humanises the snake_case string.
const ACTION_LABELS: Record<string, string> = {
  cross_fact_retrieval: "Cross-fact retrieval",
  account_hard_deleted: "Account hard-deleted",
  persona_approved: "Persona approved",
  persona_rejected: "Persona rejected",
  user_suspended: "Account suspended",
  user_unsuspended: "Account un-suspended",
  feed_post_approved: "Feed post approved",
  feed_post_rejected: "Feed post rejected",
};

function humanise(action: string): string {
  return ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

function maskIp(ip: string | null): string {
  if (!ip) return "—";
  // Mask the last octet of IPv4; truncate to /48 for IPv6 readability.
  if (ip.includes(".")) {
    const parts = ip.split(".");
    if (parts.length === 4) return `${parts.slice(0, 3).join(".")}.•`;
  }
  if (ip.includes(":")) {
    return `${ip.split(":").slice(0, 3).join(":")}::•`;
  }
  return "•";
}

export function AuditLog({ rows }: { rows: AuditRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Nothing in the last 30 days. Entries appear here when you (or someone
        admin-side) take an action against your account — cross-fact pulls,
        moderation outcomes, suspensions, deletions.
      </p>
    );
  }

  return (
    <ul className="flex flex-col divide-y rounded-md border border-input text-sm">
      {rows.map((row) => {
        const when = new Date(row.created_at);
        return (
          <li key={row.id} className="flex flex-col gap-1 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{humanise(row.action)}</span>
              <span className="text-xs text-muted-foreground">
                {when.toLocaleString()}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
              <span>
                {row.entity_type}
                {row.entity_id ? ` · ${row.entity_id.slice(0, 12)}` : ""}
              </span>
              <span>IP {maskIp(row.ip_address)}</span>
            </div>
            {row.metadata && Object.keys(row.metadata).length > 0 ? (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">
                  details
                </summary>
                <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-xs">
                  {JSON.stringify(row.metadata, null, 2)}
                </pre>
              </details>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
