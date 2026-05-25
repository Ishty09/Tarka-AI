# OSS toolkit — curated, opinionated

Rabbi asked for a broad GitHub scout. This is the filtered list:
repos that solve real gaps in Quarrel's stack, not just "trending" or
"would be cool". Each entry includes the specific gap it fills + a
honest recommendation on **when** to integrate.

The default answer is "not now, not yet" — we already have a working
architecture per CLAUDE.md §3 and adding deps before launch slows us
down. The exceptions are flagged 🔥 **Integrate before launch**.

---

## 🔥 Integrate before launch (real gaps in our stack)

### 1. **promptfoo** — anti-sycophant eval harness
- https://github.com/promptfoo/promptfoo (MIT, ~6k stars)
- **Gap it fills:** we claim "anti-sycophant AI" but have zero automated
  tests proving it. Today, a prompt regression that makes our persona
  agree with users silently ships to production.
- **Integration:** add `evals/` dir. YAML test cases for each persona
  ("user expresses obviously wrong belief, assert the reply pushes
  back"). Run on every PR via GitHub Actions.
- **Effort:** 1 day to set up + 50 test cases.
- **Decision gate:** §28 launch-day requires demonstrating the
  anti-sycophant claim under adversarial input.

### 2. **react-email** — transactional email rendering
- https://github.com/resend/react-email (MIT, by Resend, our email provider)
- **Gap it fills:** §14 lists 14 email templates. Jinja2 in workers
  works but doesn't preview/iterate easily. React Email lets us
  write JSX, preview in dev, then render to HTML for Resend.
- **Integration:** `packages/emails/` workspace. Templates as React
  components. Workers call a small render endpoint OR we ship a
  pre-rendered template per language.
- **Effort:** half-day to set up + 1 day to migrate the 14 templates.
- **Why now:** Resend natively supports it, and email rendering bugs
  surface only in production (no localhost preview today).

### 3. **assistant-ui** — chat component library
- https://github.com/assistant-ui/assistant-ui (MIT, ~3k stars)
- **Gap it fills:** our chat UI in `apps/web/app/(app)/chat/` is
  hand-rolled. Streaming display, message regeneration, copy-button,
  edit-and-retry, code blocks — all things assistant-ui has built and
  polished. Lots of accessibility/UX details we'd get for free.
- **Integration:** swap our `<ChatStream/>` for assistant-ui's
  `<Thread/>` primitive. Keep our streaming backend.
- **Effort:** 1 day swap-in + visual QA.
- **Why now:** chat IS the product. UX polish on the core surface
  beats more features.

---

## ⏳ After launch, when you actually need it

### 4. **inngest** — durable background jobs
- https://github.com/inngest/inngest (Apache 2.0)
- Replaces ad-hoc cron + pg-cron when we hit concurrency limits.
  Better DX than raw cron jobs we have today (`apps/workers/jobs/`).
  Self-hostable on the same droplet via Coolify.
- **When:** after first 1k users, when batch jobs (contradictions,
  mirror reports) start to overlap or fail at scale.

### 5. **trigger.dev** — alternative to Inngest
- https://github.com/triggerdotdev/trigger.dev (Apache 2.0)
- Already in CLAUDE.md §3 as "later". Same niche as Inngest; pick one.
  Trigger has better React/Next.js DX; Inngest has better TypeScript
  durability primitives.
- **When:** same as Inngest. Pick one — don't run both.

### 6. **llm-guard** — input/output safety augment
- https://github.com/protectai/llm-guard (MIT)
- Our safety screen (`apps/workers/services/safety.py`) is one LLM
  call per turn. llm-guard adds deterministic checks (PII regex,
  prompt injection patterns, profanity) before the LLM call so
  obvious cases short-circuit without paying for an LLM round-trip.
- **When:** when LLM cost-per-turn for safety becomes >10% of total.

---

## 👀 Inspiration only — study, don't import

### 7. **librechat** — full chat platform
- https://github.com/danny-avila/LibreChat (MIT, ~22k stars)
- Multi-LLM chat with personas, voice, memory. Their persona system +
  voice integration are good prior art. Don't import — too much
  overlap with our spec, would force major refactor. Read their
  `api/server/routes/` for patterns.

### 8. **openrouter / portkey** — LiteLLM alternatives
- We picked LiteLLM. These exist; don't switch unless LiteLLM
  proves limiting. Stay focused.

### 9. **anything-llm** — local LLM chat
- https://github.com/Mintplex-Labs/anything-llm
- Their "workspace" pattern (separate chat contexts) is what we call
  Conversations. Their persona switching UX is studyable.

---

## Things we explicitly do NOT need

- **LangChain / LlamaIndex** — over-abstracted for our use. We call
  LiteLLM directly via `packages/ai`. Adding LangChain = 50KB of
  ceremony for zero benefit.
- **Vercel AI SDK alternatives** — we use Vercel AI SDK. It works.
- **Custom auth (Clerk, Auth0)** — Supabase Auth covers us.
- **Custom realtime (Liveblocks, Pusher)** — Supabase Realtime is in
  the stack already.
- **Stripe direct** — Polar.sh is the choice for BD-compatible MoR.
- **Drizzle / Prisma** — supabase-js with zod schemas in
  `packages/shared/schemas` gives us type safety without an ORM
  layer. Adding an ORM here doubles the surface area.

---

## Decision-making heuristic

Before adding ANY dep:
1. Does it solve a problem we have **today**, not a hypothetical one?
2. Does it replace ≥3 files we'd otherwise write ourselves?
3. Is it maintained (commit in last 60 days)?
4. Does it match our license (MIT/Apache OK, GPL/AGPL only for
   self-hosted services like Lago)?
5. Does it lock us into a specific vendor that's not already in §3?

Three "yes" + zero "no" → consider adding. Otherwise skip.

Pre-launch addition count goal: **≤ 3 dependencies** beyond what's
in CLAUDE.md §3. We have enough complexity already.
