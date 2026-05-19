// Server-only client for the workers admin API.
//
// Pages and server actions call these helpers; they handle the
// WORKERS_INTERNAL_SECRET + X-User-Id handshake and JSON envelopes. The
// caller-side admin gate (apps/web/app/(app)/admin/layout.tsx) ensures
// every invocation runs as an authenticated admin; workers re-verifies on
// every request, so the boundary is enforced twice.

import "server-only";
import { serverEnv } from "@/lib/env";

export type AdminFetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string };

async function adminFetch<T>({
  path,
  userId,
  init,
}: {
  path: string;
  userId: string;
  init?: RequestInit;
}): Promise<AdminFetchResult<T>> {
  if (!serverEnv.WORKERS_INTERNAL_SECRET) {
    return { ok: false, status: 503, error: "workers_internal_secret_unset" };
  }
  const res = await fetch(`${serverEnv.WORKERS_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
      "x-user-id": userId,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    return { ok: false, status: res.status, error: text || res.statusText };
  }
  return { ok: true, data: (await res.json()) as T };
}

// ----- Listings ------------------------------------------------------------

export interface PersonaPending {
  id: string;
  slug: string;
  name: string;
  owner_id: string | null;
  category: string;
  visibility: string;
  moderation_status: string;
  system_prompt: string;
  created_at: string;
}

export interface FeedPostPending {
  id: string;
  user_id: string;
  conversation_id: string;
  message_id: number;
  caption: string | null;
  moderation_status: string;
  visibility: string;
  created_at: string;
}

export interface SafetyIncident {
  id: number;
  user_id: string | null;
  conversation_id: string | null;
  message_id: number | null;
  category: string;
  verdict: string;
  action_taken: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface UserSummary {
  id: string;
  username: string;
  display_name: string | null;
  tier: string;
  is_admin: boolean;
  is_suspended: boolean;
  suspension_reason: string | null;
  created_at: string;
  data_deletion_requested_at: string | null;
}

export async function fetchPendingPersonas(userId: string) {
  return adminFetch<{ personas: PersonaPending[] }>({
    path: "/admin/personas/pending",
    userId,
  });
}

export async function fetchPendingFeedPosts(userId: string) {
  return adminFetch<{ posts: FeedPostPending[] }>({
    path: "/admin/feed/pending",
    userId,
  });
}

export async function fetchIncidents(
  userId: string,
  opts: { category?: string; unreviewedOnly?: boolean } = {},
) {
  const params = new URLSearchParams();
  if (opts.category) params.set("category", opts.category);
  params.set("unreviewed_only", String(opts.unreviewedOnly ?? true));
  return adminFetch<{ incidents: SafetyIncident[] }>({
    path: `/admin/incidents?${params.toString()}`,
    userId,
  });
}

export async function fetchUsers(userId: string, query?: string) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const qs = params.toString();
  return adminFetch<{ users: UserSummary[] }>({
    path: `/admin/users${qs ? `?${qs}` : ""}`,
    userId,
  });
}

// ----- Mutations -----------------------------------------------------------

export async function moderatePersona(
  userId: string,
  body: { persona_id: string; action: "approve" | "reject" | "flag"; notes?: string },
) {
  return adminFetch<{ status: string }>({
    path: "/admin/personas/moderate",
    userId,
    init: { method: "POST", body: JSON.stringify(body) },
  });
}

export async function moderateFeedPost(
  userId: string,
  body: { post_id: string; action: "approve" | "reject" | "remove"; notes?: string },
) {
  return adminFetch<{ status: string }>({
    path: "/admin/feed/moderate",
    userId,
    init: { method: "POST", body: JSON.stringify(body) },
  });
}

export async function suspendUser(
  userId: string,
  body: { user_id: string; reason: string },
) {
  return adminFetch<{ status: string }>({
    path: "/admin/users/suspend",
    userId,
    init: { method: "POST", body: JSON.stringify(body) },
  });
}

export async function unsuspendUser(userId: string, body: { user_id: string }) {
  return adminFetch<{ status: string }>({
    path: "/admin/users/unsuspend",
    userId,
    init: { method: "POST", body: JSON.stringify(body) },
  });
}

export async function reviewIncident(
  userId: string,
  body: { incident_id: number; notes?: string },
) {
  return adminFetch<{ status: string }>({
    path: "/admin/incidents/review",
    userId,
    init: { method: "POST", body: JSON.stringify(body) },
  });
}
