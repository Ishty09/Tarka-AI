# Safety triage

CLAUDE.md §1.5 + §6.6 + §7.5: every inbound message passes through the
safety screen, which returns `safe | crisis | abuse |
minor_self_sexualization | jailbreak`. Non-safe verdicts persist a row
in `safety_incidents` and short-circuit the model.

This runbook covers what humans do *after* the automated handling.

## Daily queue

Every morning (UTC), open `/admin/incidents` and triage rows from the
last 24 hours. Filter by verdict:

| Verdict                       | Frequency target | Action                                                              |
| ----------------------------- | ---------------- | ------------------------------------------------------------------- |
| `crisis`                      | All — every row  | See "Crisis triage" below.                                          |
| `abuse`                       | All — every row  | See "Abuse triage" below.                                           |
| `minor_self_sexualization`    | All — every row  | See "Minor safety" below — non-negotiable; do not batch.            |
| `jailbreak`                   | Sample 10/day    | Note pattern; if a single user submitted > 5 in 24h, suspend account. |

## Crisis triage

For each `crisis` row:

1. Open the conversation in the admin panel. Read the message + the AI's
   refusal turn that fired.
2. If the user has an `emergency_contact_email` set on profile AND there
   are ≥ 2 crisis incidents in 24h, the worker will have already fired
   the `emergency_contact_notification` email — verify it sent.
3. Verify the in-app crisis modal showed locale-appropriate hotlines
   from `crisis_hotlines` (§15). If a hotline failed to render (locale
   mismatch), file a bug.
4. Mark the incident **reviewed** in the admin panel. Reviewing is just
   a stamp; we don't change the user's account state.
5. If the user has reached out repeatedly (5+ crisis signals in 7 days),
   send a personal email from `support@quarrel.ai` offering a phone
   call. The script lives at `infra/runbooks/templates/crisis-followup.txt`
   (TBD — create on first use).

Never:

- Reach out using language that implies clinical assessment ("you seem
  depressed", "you may want to see a therapist"). We can suggest
  *professional help is available*; we cannot diagnose.
- Forward the message content to anyone outside the company.

## Abuse triage

For each `abuse` row:

1. Read the user's message. Distinguish:
   - **Abuse described** (user is being abused by someone else): offer
     hotlines, do not contact the alleged abuser.
   - **Abuse threatened** (user describing intent to harm another): see
     "Threatened-violence triage" below.
2. If a *minor* is described as being abused, this is a mandatory-report
   trigger in many jurisdictions. Refer to legal counsel via
   `legal@quarrel.ai`; document the timestamp + the verbatim message in
   a sealed admin note.
3. Mark reviewed; the row is retained per §16 (24 months).

## Threatened-violence triage

For credible specific threats of violence:

1. Suspend the account immediately (admin panel → "Suspend user", with
   reason `threat_of_violence`).
2. Preserve the conversation (no deletion).
3. Notify counsel via `legal@quarrel.ai` — they decide on law-enforcement
   referral.
4. Mark the safety_incident with action `escalated_external`.

Speed matters more than perfect classification — if in doubt, suspend
first and review with counsel after.

## Minor safety (`minor_self_sexualization`)

Mandatory immediate action:

1. The system has already terminated the conversation. Verify by reading
   the safety_incident row.
2. **Account termination**: admin panel → "Terminate account" (not
   suspend — full delete). Reason `minor_safety_violation`.
3. **Report to NCMEC** via the CyberTipline (https://report.cybertip.org)
   within 24 hours.
4. Preserve the message + minimal user metadata (account ID, IP at
   submit) in a sealed `safety_incidents.action_taken = 'reported_ncmec'`
   row before the account delete cascades.
5. Email `legal@quarrel.ai` with the report receipt.

This is the only path where account termination precedes the §58
30-day grace.

## Jailbreak triage

Jailbreak verdicts are mostly noise. Look at the daily count and the
top-10 users by jailbreak count.

- ≤ 3 attempts: ignore.
- 4-10 attempts in 24h from one user: send the user a one-time warning
  via in-app banner.
- > 10 in 24h: suspend, with reason `jailbreak_repeated`.
- If a single jailbreak attempt **succeeded** (the safety screen returned
  "safe" but the model produced clearly violating output), file a P1
  bug in the safety screen — the classifier is failing.

## Roast Feed moderation

Separate queue at `/admin/moderation`. Auto-classifier marks posts
`approved` / `flagged`. Manual review on flagged:

- Approve: visibility = public.
- Reject: visibility = removed; row stays for audit.
- Remove (previously approved): same as reject + send the user a one-line
  email explaining which AUP clause they violated.

Moderation decisions write to `audit_log` via the admin service.

## Persona marketplace moderation

Same queue, `kind = persona`. Specific checks:

- System prompt impersonates a real, identifiable private individual →
  reject.
- System prompt instructs the model to bypass safety screens → reject +
  suspend the creator (this is jailbreak weaponization).
- Otherwise approve.

## Appeals

Users can appeal any moderation outcome by emailing
`appeals@quarrel.ai`. A human reviews within 7 days:

1. Read the original incident + reviewer notes.
2. Read the appeal.
3. If overturned: revert the action (un-suspend, restore the post,
   re-approve the persona) and email the user.
4. If upheld: email the user with the specific policy clause violated.

Appeals receipts log to `audit_log` as `action = 'appeal_reviewed'`.

## What we never do

- **Read user messages without an incident trigger.** The admin panel
  shows messages bound to a safety_incident; randomly reading user chats
  for curiosity is a fireable offense.
- **Forward user content to third parties** outside the §16
  subprocessors and lawful authorities.
- **Discuss specific user safety events in public** — even in
  generalised post-mortems on the blog, scrub all identifying details.
