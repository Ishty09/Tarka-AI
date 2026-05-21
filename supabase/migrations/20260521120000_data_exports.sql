-- §27 step 57 — GDPR data-export pipeline.
--
-- Stores per-user export requests + their generated artefacts. The actual
-- JSON blob lives in Supabase Storage under the private `data-exports`
-- bucket; this table tracks intent + status + the signed URL that the
-- email pointed the user at.
--
-- Lifecycle: pending → processing → ready → expired.
--          ↘ failed (operator-visible; the user is told to retry).

create table data_export_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  status text not null default 'pending' check (
    status in ('pending', 'processing', 'ready', 'failed', 'expired')
  ),
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  ready_at timestamptz,
  failed_at timestamptz,
  expires_at timestamptz,
  storage_path text,        -- bucket-relative path of the JSON blob
  download_url text,        -- signed URL, regenerated if needed
  byte_size integer,
  row_counts jsonb,         -- {profiles: 1, conversations: 12, ...} for the receipt
  error_message text,
  email_sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_data_export_user
  on data_export_requests(user_id, requested_at desc);
create index idx_data_export_pending
  on data_export_requests(requested_at)
  where status in ('pending', 'processing');
create index idx_data_export_expiring
  on data_export_requests(expires_at)
  where status = 'ready';

alter table data_export_requests enable row level security;

-- Owner can see their own requests (for /settings/data history).
create policy data_export_requests_owner_select
  on data_export_requests for select
  using (user_id = auth.uid());

-- Owner can create a new request from the app.
create policy data_export_requests_owner_insert
  on data_export_requests for insert
  with check (user_id = auth.uid());

-- Updates + deletes happen only via service-role (workers). No policy
-- for those — RLS denies them for authenticated callers, which is the
-- desired posture.

-- ----- Storage bucket -------------------------------------------------------
--
-- Private bucket. The worker writes files via service-role; users never
-- see object URLs directly — they download via the signed URL embedded
-- in the data_export_ready email.

insert into storage.buckets (id, name, public)
values ('data-exports', 'data-exports', false)
on conflict (id) do nothing;

-- No public read policy. The worker is the only writer, and signed URLs
-- handle reads — neither needs a row-level policy.
