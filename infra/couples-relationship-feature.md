# Couples / Relationship Build-up — flagship subscription feature

Rabbi's strategic pick: make Quarrel the **continuous relationship
coach** for couples (boyfriend/girlfriend, husband/wife). Not a
therapist app, not a date-night gimmick — the place where two people
go when they want an honest third party who's tracked their patterns
over time.

## Why this earns subscription

The four levers all converge:
- **Effort scoring** answers "is my partner doing enough?"
- **Dispute arbitration** answers "who's actually wrong?"
- **Pattern coach** answers "why does this fight keep happening?"
- **Future projection** answers "should we stay together?"

Most couples-tech is either reactive (only used in crisis) or
gimmicky (date-night question lists). Quarrel sits between: ambient
tracking + on-demand arbitration. Both partners pay because both
benefit — the AI is the only entity that sees both sides.

## Architecture vs what exists

What's already built (from §9.3.1):
- `couple_links` table — pairs two users, triple-opt-in for cross-fact
  retrieval
- Shared conversation backed by `the_therapist` persona
- Workers `services/couples.py` handles session setup
- Web pages: `/couples`, `/couples/invite`, `/couples/[linkId]`,
  `/couples/join`

What this feature adds:
1. **`couple_disputes`** — both submit perspectives independently;
   when both are in, AI produces a structured verdict both see.
2. **`couple_health_logs`** — daily 1-minute check-ins per partner
   feed an effort dashboard.
3. **`couple_reports`** — weekly auto-summary (cron, Sunday).
4. **`couple_issues`** — recurring themes detected from disputes +
   shared chat, with status tracking.

This doc ships **disputes** as the MVP — sharpest demonstration of
the value, ~3 hours build. Health logs / reports / issues land in
subsequent commits.

## Disputes — flow

1. Either partner clicks "New dispute" on `/couples/[linkId]`.
2. Form: title (e.g. "Sunday night fight about money") + their
   perspective. Submitted privately.
3. Partner gets a push + sees "Awaiting your perspective" on link.
4. Partner opens, reads ONLY the dispute title (not the other side's
   text), submits their own perspective.
5. When second perspective submitted, workers route triggers
   `dispute_arbitrator.py` synchronously (~5s LLM call).
6. Both partners see the same arbitration: structured JSON rendered
   as readable verdict.
7. Either can mark "Resolved" — closes the dispute, archives for
   future pattern detection.

### Arbitration verdict shape

```json
{
  "summary": "Neutral 1-2 sentence framing of the fight",
  "who_escalated_first": "a" | "b" | "both" | "unclear",
  "what_a_actually_wanted": "...",
  "what_b_actually_wanted": "...",
  "patterns_detected": ["pattern 1", "pattern 2"],
  "advice_for_a": ["step 1", "step 2"],
  "advice_for_b": ["step 1", "step 2"],
  "what_to_do_next": "concrete action both should take in 24h",
  "confidence": 0-10
}
```

`confidence` reflects how one-sided the info is. <5 means the AI
flags "I'd like more context from both of you" — anti-sycophant
honesty, not fake certainty.

### Privacy

- Each perspective is private until the other submits — neither
  partner can read the other's perspective before they've written
  their own. This prevents anchoring.
- After arbitration, BOTH perspectives are visible to both partners.
  By submitting, you're agreeing to share with your partner.
- Either partner can revoke the couple link → cascade-deletes all
  disputes (per existing `on delete cascade`).

### RLS

```sql
-- Read: any link member can see disputes on the link
-- Insert: any link member can create a dispute
-- Update: any link member can update (add perspective, mark resolved)
```

We rely on row-level data (`perspective_a_user_id` etc.) for who-can-
edit-what at the application level, since RLS on a 2-perspective row
is awkward. Workers double-checks on update.

## LLM prompt — anti-sycophant arbitration

```
You are an experienced couples therapist with anti-sycophant rules.
Two partners are in conflict. Each submitted their side
independently. Your job: synthesize both perspectives and produce a
JSON verdict.

Rules:
1. Both partners will see this verdict. Be honest with both — never
   flatter.
2. Identify who escalated FIRST. Acknowledge that both usually
   contribute.
3. Distinguish what each was SAYING vs what they ACTUALLY wanted.
4. Spot patterns (this fight is about X but feels like Y).
5. Concrete next steps, separate per partner.
6. Confidence 0-10. Be honest when info is one-sided (low score).
7. Reply in the language of the perspectives provided. If they're in
   different languages, default to the language Partner A used.
8. Output ONLY valid JSON. No prose around it.

Schema: {...}

Partner A's perspective:
{a_text}

Partner B's perspective:
{b_text}
```

## Future increments (next commits)

### Daily effort logging (Week 2)
- 1-min check-in per partner per day
- Slider: "How much effort did you put in today?"
- 1 sentence each: "best thing partner did" + "what frustrated me"
- Dashboard: 7-day effort graph for both, side-by-side

### Weekly couples report (Week 3)
- Cron Sunday 09:00 in each partner's TZ
- Synthesis of disputes + check-ins + shared chat
- Top 3 themes, top 1 pattern, one experiment for the week

### Open issues tracker (Week 4)
- Auto-extracted recurring themes (money, in-laws, household, etc.)
- Status: discussed / agreed / resolved / recurring
- Reminder check-ins if not addressed in 30 days

### Pre-conversation coaching (Week 5)
- Before a hard talk, each partner gets private prep
- Their own talking points + what their partner might say + de-
  escalation paths

## Tier mapping

| Feature | Free | Pro | Max |
|---|---|---|---|
| Couple link | – | 1 link | 3 links |
| Disputes per month | – | 5 | unlimited |
| Daily effort log | – | ✓ | ✓ |
| Weekly couples report | – | ✓ | ✓ + on-demand |
| Open issues tracker | – | last 10 | full history |
| Pre-conversation coaching | – | – | ✓ |
| Future projection (6mo) | – | quarterly | monthly |

Free tier gets zero couples — the entire feature is paid. This is the
strongest possible "upgrade to Pro" hook for users in serious
relationships.
