-- §12.2 — per-event notification preferences.
--
-- Stored as { channel: { category: bool } } where channel is "push" or
-- "email" and category is one of the categories defined in
-- packages/shared/src/constants.ts (NOTIFICATION_CATEGORIES). A
-- missing key means "allowed"; explicit `false` mutes that
-- channel+category combination. The two global toggles
-- notification_push / notification_email remain authoritative master
-- switches that override these per-category prefs.
--
-- Free-form JSONB on purpose — categories evolve; check-constraining
-- the shape here would force a migration every time we add a topic.
-- Validation lives in app code (TS in web, Python in workers).

alter table profiles
  add column if not exists notification_preferences jsonb
    not null default '{}'::jsonb;
