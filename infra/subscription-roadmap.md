# What makes Quarrel worth $10/mo

Rabbi's question is the right one: "argues back" is a tweet, not a
subscription. People pay for AI that **changes outcomes in their
life**, not for entertainment. This doc names the four jobs that
actually pull money out of wallets, picks the 6 features that map to
those jobs, and ranks the top 3 to build first.

## Diagnosis: why the current spec is shareable but not subscribable

The §2 pillars (Argue / Roast / Mediate / Remember) are **positioning**,
not **jobs**. Positioning makes people install. Jobs make them pay.

What we have today:
- Argue mode → fun for 3 sessions, then "OK I get it"
- Roast My X → high virality, near-zero retention
- Cultural personas → installation incentive, not usage incentive
- Wagers → very subscription-worthy but currently buried
- Mirror / Eulogy → potential, but weekly/quarterly cadence is too slow

What's MISSING is anything that the user **wakes up needing to use
because skipping it would hurt them**. That's the lever.

## The 4 jobs that drive subscription (ranked by paid-conversion strength)

### Job 1: "Help me make a decision I'm afraid to make"
The single biggest pull-out-credit-card moment. People pay for
permission, confidence, or a structured reframe before quitting jobs,
ending relationships, moving cities, raising prices.

Existing: Council (excellent, but one-shot), Decision Killer.
Missing: **Decision Replay** — predictions vs outcomes tracked over
time. Most addictive feature you can ship for this job.

### Job 2: "Coach me through a hard conversation I can't avoid"
Salary negotiation. Breakup. Setting a boundary with a parent. Asking
for an investment. These happen on calendar deadlines; people pay
before, during, after.

Existing: Negotiation Sparring (rehearsal only).
Missing: **Live Mode** (paste the other side's actual messages mid-
conversation, get instant counter) + **Debrief** (after, what worked).
The three-act flow.

### Job 3: "Hold me accountable when I'd skip on my own"
People pay for the friction. Money on the line + a witness who calls
them out.

Existing: Wagers (with anti-charities), Drill Sergeant streaks.
Missing: **Social witnesses** (invite specific friends to see commits,
not anonymous feed) + **smart push that knows your schedule** instead
of a fixed daily roast time.

### Job 4: "Show me a pattern in my own thinking I can't see"
The "wow, I do that?" moment. Highly addictive once data accumulates —
which is why retention compounds.

Existing: Contradiction Wall, Mirror Mode, Eulogy.
Missing: **Daily anchor ritual** that feeds the data engine + an
**Insights dashboard** that visualizes patterns weekly with
shareability (most viral content surface we can ship).

## The 6 features ranked by (paid-conversion impact ÷ build cost)

| # | Feature | Job | Impact | Cost | Ratio |
|---|---|---|---|---|---|
| 1 | **Daily Anchor (AM/PM ritual)** | 4 | High | Low | 🟢🟢🟢 |
| 2 | **Text Triage** (paste any message → decode + reply) | 2 | Very High | Low | 🟢🟢🟢 |
| 3 | **Decision Replay** (predictions vs outcomes) | 1 | High | Medium | 🟢🟢 |
| 4 | **Hard Conversation Live Mode** | 2 | Very High | Medium | 🟢🟢 |
| 5 | **Insights Dashboard** (Mirror Mode++) | 4 | Medium | Medium | 🟢 |
| 6 | **Social Wagers** (named friends as witness) | 3 | Medium | High | 🟡 |

## Top 3 to build first — concrete specs

### 1. Daily Anchor 🌅🌆

**Hook:** 2 min AM, 2 min PM. Builds the data engine that makes every
other Quarrel feature smarter over time.

**AM prompt (push at user's preferred morning time):**
> What's the ONE thing today you'd hate to admit you skipped?
> Why might you skip it?

**PM prompt (push at evening):**
> What did you avoid today?
> What did you tell yourself to make it OK?

**Wire-up:**
- New table: `daily_anchors(user_id, date, am_response, pm_response,
  skipped_count)` — RLS self.
- Two-message form, no chat UI — just a journal-style entry.
- Each entry runs through fact extraction → `user_facts`. Now the
  contradiction engine has real fuel.
- Streak counter visible in sidebar header.
- Skipping 3 days → Drill Sergeant escalation kicks in.

**Why it earns subscription:**
- Daily usage frequency = high
- Skipping has visible consequence (broken streak)
- Free tier: AM only. Pro: AM + PM. Max: AM + PM + weekly synthesis.
- Feeds Contradictions / Mirror / Eulogy — they become 10x richer
- 2 min/day is the sweet spot — short enough to do, long enough to
  matter

**Build cost:** 2 days (1 migration, 1 worker job, 1 UI page, 2 push
templates). Tiny relative to its retention impact.

### 2. Text Triage 💬

**Hook:** "Paste any message you got. I'll decode what they actually
mean and write your reply."

This is THE feature where people pay $10 to avoid making one career-
ending response to a boss email.

**Flow:**
1. User pastes a message (max ~2000 chars): WhatsApp from partner,
   Slack from boss, email from landlord, etc.
2. Optional context: relationship + emotional weight (1-5)
3. AI returns three blocks:
   - **What they're actually saying** (emotional decode, 2 sentences)
   - **What you might be missing** (the angle the user can't see)
   - **Three reply options** (de-escalate / hold ground / pivot)
4. Each option has a "copy" button + "edit and try variations" link
5. If user picks an option and replies, optional follow-up: "How did
   they respond?" → trains the relationship model for that person

**Wire-up:**
- New tool route `/tools/text-triage`
- Workers `services/text_triage.py` — single LLM call with structured
  output
- Optional `relationships(user_id, contact_name, communication_pattern,
  history_summary)` table for repeat use with the same person — big
  retention multiplier
- Free tier: 5/month. Pro: 100/month. Max: unlimited + relationship
  memory.

**Why it earns subscription:**
- High-stakes moment (people will pay one-time before a hard text)
- Repeat usage (everyone has multiple ongoing hard conversations)
- The "Did they respond?" loop creates a moat (the AI remembers how X
  always responds and tailors future drafts to her specifically)

**Build cost:** 3 days (1 worker route, 1 service, 1 UI page,
relationships table optional).

### 3. Decision Replay 🔮

**Hook:** "Every big decision goes into a vault. We check back in
1 month, 3 months, 1 year. You see what you predicted vs what
actually happened."

This is the feature people **share screenshots of**. Most viral
post-launch content surface.

**Flow:**
1. User describes a decision they made (job offer accepted, breakup,
   move, investment, etc.)
2. Quarrel asks 3 calibration questions:
   - What outcome do you expect in 3 months?
   - What's the worst case you're not admitting?
   - What's the one variable that, if it changed, would make this
     wrong?
3. Saved as a `decision_replay` row with `predicted_at` + `check_in_at`
4. Push at 1m, 3m, 12m: "You predicted X. What's actually happening?"
5. User updates → AI compares prediction vs reality → generates a
   1-paragraph honest debrief
6. **Shareable card**: "I predicted this. Here's what actually
   happened." (with optional anonymization) — public Roast Feed
   variant.

**Wire-up:**
- `decision_replays(id, user_id, decision_text, predictions jsonb,
  predicted_at, check_in_dates date[], outcomes jsonb)`
- Workers cron `decision_replay_followup.py` to surface the prompt at
  check-in dates
- UI: `/decisions` list + `/decisions/[id]` detail with timeline
- Shareable artifact generator (image with the prediction vs outcome)

**Why it earns subscription:**
- Free tier: 1 active replay. Pro: 10. Max: unlimited.
- Per-decision check-ins compound — users stay because their data
  is locked here
- Shareable artifacts drive organic acquisition
- "I want to be the kind of person who keeps decisions honest" is a
  strong identity hook

**Build cost:** 4 days (migration, worker cron, 2 UI pages,
shareable artifact generator).

## Tier mapping (revised from §8.1)

| Feature | Free | Pro | Max |
|---|---|---|---|
| Daily Anchor (AM only) | ✓ | – | – |
| Daily Anchor (AM + PM) | – | ✓ | ✓ |
| Daily Anchor weekly synthesis | – | – | ✓ |
| Text Triage | 5/mo | 100/mo | unlimited |
| Triage relationship memory | – | – | ✓ |
| Decision Replays | 1 active | 10 active | unlimited |
| Decision shareable artifact | watermarked | clean | clean + variants |
| Voice journal (Max only) | – | – | ✓ |
| Hard Conversation Live Mode | – | ✓ | ✓ |
| Insights Dashboard | static weekly | weekly + on-demand | full + trends |

This pushes paid conversion from "I want unlimited messages" (weak
hook) to "I want my relationships / decisions / patterns tracked"
(strong hook).

## What we should NOT build

- More personas (we have 25; users use 3 max)
- More tools that are one-shot (Cope Detector etc. are nice but don't
  drive return visits)
- More viral/share surfaces (Roast Feed is enough; spend novelty
  budget elsewhere)
- Voice ASAP (deferred per §3; revisit after Daily Anchor proves
  ritual works)
- Mobile app pre-launch (Expo build adds 2 weeks; ship web first)

## Build order — concrete

If we ship one per week:

**Week 1:** Daily Anchor. Cheapest, biggest retention lift.
**Week 2:** Text Triage. Highest paid-conversion lift per build hour.
**Week 3:** Decision Replay. Viral acquisition + lock-in.
**Week 4:** Insights Dashboard upgrade.
**Week 5:** Hard Conversation Live Mode.
**Month 2+:** Social Wagers, Voice journal.

By month 2, the product justifies $10/mo via concrete jobs done. The
"argues back" tagline becomes the wedge, not the whole product.

## Decision

Rabbi picks ONE of the top 3 — Daily Anchor / Text Triage / Decision
Replay — and we build it next. My recommendation: **Daily Anchor**.
It's the cheapest, most addictive, and every other feature gets
smarter from the data it generates.
