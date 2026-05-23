# Product Hunt launch

CLAUDE.md §27 step 74 — schedule and run the PH launch. §27 step 75 is
the public launch; PH is the activation event that drives it.

This runbook walks T-14 days through T+24h. Read top-to-bottom before
scheduling; reference top-to-bottom on launch day.

## TL;DR timing

- **Post at 00:01 PST** (08:01 UTC). PH's 24-hour ranking window starts
  then; later posts compete against fewer hours of upvote accumulation.
- **Stay live on launch day.** Reply to every comment within 30 min.
  This is the single biggest predictor of ranking.
- **Pick a Tuesday-Thursday.** Monday is noisy from weekend backlog;
  Friday and weekends get less attention.

## T-14 days — assets

All assets live under `infra/launch/product-hunt/` (create when staging).

### Required

| Asset                    | Format         | Specs                                                                   |
| ------------------------ | -------------- | ----------------------------------------------------------------------- |
| Logo                     | PNG/SVG, square| 240×240, transparent bg. Keep margin so the PH circular crop doesn't clip. |
| Tagline                  | text           | ≤ 60 chars. Variant A: "The AI that won't let you lie to yourself." Variant B: "Anti-sycophant AI: argue, roast, remember every contradiction." |
| Description              | text           | ≤ 260 chars. "Quarrel is the AI companion engineered to disagree. It argues, roasts you into action, mediates relationship disputes, and tracks every contradiction you make. 25 cultural personas. Pricing from free." |
| Gallery images (3-6)     | PNG, 1270×760  | Hero shot, chat in argue mode with a contradiction callout, Council results, Roast My X demo, Pricing card, Mirror Report sample. |
| Demo video (optional)    | MP4, ≤ 60s     | 30s screencap of a real chat round-trip ending in a contradiction surfacing. Voiceover optional. |

### Asset checklist

- [ ] All gallery images are real product screenshots, not mockups.
- [ ] No PII or test-account names visible.
- [ ] Light + dark mode mix (PH viewers split roughly 50/50).
- [ ] Tagline runs through a non-native English speaker for clarity
      check.
- [ ] Description ends with a CTA: "Free tier 15 messages/day. No card.
      Try it →"
- [ ] OG image (`apps/web/public/og.png`, 1200×630) updated with
      launch-day branding.

## T-7 days — hunter + first comments

1. **Hunter.** A high-follower PH hunter doesn't guarantee top 5 anymore
   but lifts the early-hour visibility. If you have one lined up, brief
   them with: tagline, 1-paragraph pitch, gallery, 3 talking points.
   If not, self-hunt — works fine for products that already have a
   waitlist or beta cohort.
2. **First comment (maker's intro).** Draft now, post within 5 minutes
   of going live. Template:

   > Hey Hunters 👋
   >
   > I'm Rabbi, the founder of Quarrel AI. I built this because every AI
   > chat I used was optimised to agree with me, and that made me
   > worse at thinking.
   >
   > Quarrel argues back. It pushes against your reasoning, roasts
   > targets you submit (LinkedIn, resume, your last code commit), and
   > remembers what you said two weeks ago so you can't quietly walk
   > back a position.
   >
   > It runs through OpenAI + Anthropic with a safety classifier on
   > every message, lives at quarrel.ai, and the free tier gives you 15
   > messages a day to try it. Happy to answer anything in the
   > comments today.
   >
   > — Rabbi

   Edit before posting — the template is a starting point. Don't open
   with "Excited to launch" or "Thrilled to share". Both flag as
   marketing-speak in 2026 PH culture.

3. **Pre-launch comment prep.** Draft replies to 5 predictable
   questions so you can ship them within 30s of seeing the comment:
   - "How is this different from ChatGPT with a custom prompt?"
   - "What stops it from being mean to vulnerable users?"
   - "Pricing seems steep / cheap" (both)
   - "Open source?"
   - "Mobile?"

## T-3 days — pre-launch

- [ ] Schedule the launch in the PH dashboard. Don't post manually on
      launch day — scheduling avoids time-zone mistakes.
- [ ] Confirm everyone on the beta cohort knows the launch date.
      Promise nothing about upvoting, but make it easy to find the
      page on launch day.
- [ ] Add the launch banner to the marketing site by setting
      `NEXT_PUBLIC_PRODUCT_HUNT_URL` in Vercel. The hero gets a
      "We're live on PH" pill; flip the env var to the empty string to
      hide it again.
- [ ] Pre-write a launch-day X post (no hashtags, link in the first
      line, character count under 270).
- [ ] Notify Polar support and Supabase support that the launch is
      happening so they don't panic if traffic doubles overnight.

## T-0 — launch day

### 00:01 PST (08:01 UTC) — go live

- Confirm the post is up. Refresh PH's `/featured` page and check the
  product appears.
- Post the maker's intro comment immediately.
- Pin the PH URL in the team's ops channel.

### 00:30 - 23:00 PST — sustained engagement

- **Comment reply SLA: 30 minutes**, every comment, every day. The PH
  ranking algorithm weighs comments + upvotes from people who reply
  vs people who lurk.
- For each substantive question, draft a reply that:
  - Acknowledges the specific concern (don't generic-reply).
  - Cites a concrete feature or design decision from CLAUDE.md (e.g.,
    "We use a separate safety classifier — see /legal/ai-disclosure/en
    §5 for the full screen flow").
  - Ends with one question back to the commenter when natural. PH
    rewards threads.
- **Monitor:** `/admin/retention` (cohort_tag = `product-hunt` set up
  pre-launch), `/admin/incidents`, Sentry, UptimeRobot.
- **If anything breaks:** triage per `incident-response.md`. The
  status page post is mandatory within 10 minutes regardless of
  launch-day workload.

### Quotas + budget

- LiteLLM proxy has rate limits per virtual key (§23). For launch day
  bump the production virtual key's RPM × 3 in the LiteLLM admin UI
  before going live. Drop it back at T+48h.
- OpenAI + Anthropic spend will spike. Set spend alerts to 2× normal
  daily and watch the bills.

### Cross-promotion

- Post on X with the PH link in the first line (algorithm penalises
  link-in-reply).
- DM the link to ~10 people who said they'd vote — don't ask. Just
  share it. Asking on PH-launch day looks desperate.
- Post in 2-3 communities where you have standing (your local hacker
  meetup Slack, the indie hackers group, etc.). Never spam Hacker
  News on a PH day; they have an unwritten rule against it.

## T+24h — post-launch

- Final upvote count + ranking position screenshotted for the retro.
- Total signups counted: `select count(*) from profiles where
  created_at > '<launch-date>' and tier_source is null` (free signups
  only; paid go through the Polar webhook).
- Net new tier conversions: count active `subscriptions` rows created
  on launch day.
- Cohort retention will be available at T+8d — see `beta-cohort.md`'s
  retention query, filter on `cohort_tag = 'product-hunt'`.

## T+7d — retro

Append a launch retro to `infra/runbooks/post-mortems/`:

- Final PH rank + upvote count.
- Total signups; tier conversion rate.
- D2-D7 retention vs the §28 ≥ 30% gate.
- 3 things that worked.
- 3 things that didn't.
- Open follow-ups with dates.

A failed launch isn't fatal — most successful indie products launched
twice on PH. If retention is good and ranking was low, schedule a
second launch in 6 months with the lessons folded in.

## Hard rules

- **No fake accounts.** PH detects them and bans products that use
  them. The 100-beta cohort is the legitimate seed audience.
- **No "vote for us" emails.** PH bans products for this. Sharing the
  link is fine; asking is not.
- **No comment removal** of legitimate criticism. Respond honestly or
  leave it alone.
- **No deploy on launch day** unless it's a P1 hotfix. The deploy
  freeze in `deploy.md` applies.
- **Status page first, status page first, status page first.** If
  anything user-visible breaks, the public status post predates the
  ops-channel post.
