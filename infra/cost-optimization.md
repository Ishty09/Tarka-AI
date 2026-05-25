# Cost optimization — OSS swaps that don't hurt quality

Pre-launch + post-launch lever list, ordered by impact. Numbers based on
projected 1k DAU × 30 turns/day × ~500 tokens in/out per turn (~15M
tokens/month).

## TL;DR — biggest levers

| Lever | Monthly save | Quality risk | When to do |
|---|---|---|---|
| **Route safety classifier to Groq/Llama** | ~$45 | None — classification | Today |
| **Default to Claude Sonnet 4.6 over GPT-5 for argue** | ~$200 | Low — Sonnet quality is comparable | After 1 week of GPT-5 baseline metrics |
| **Aggressive prompt caching** | ~$80 | None | This week |
| **Batch API for nightly contradiction job** | ~$40 | None — async OK | After job reliability proven |
| **Self-host Sentry → GlitchTip** | ~$26 | Tiny — same UX | When errors > 5k/mo |
| **Self-host Resend → Listmonk** | ~$20 | Low | When email > 100/day (free tier cap) |

**Total realistic monthly save by month 3: ~$400.**

## 1. LLM tier — the biggest cost

### Safety classifier → Groq (Llama 3.3 8B)
- Current: GPT-5-mini, ~$0.15/1M input, $0.60/1M output
- Groq Llama 3.3 8B: ~$0.05/1M input, $0.08/1M output
- Safety screen runs on EVERY inbound message — ~15M tokens/month
- **Savings: ~$45/mo**
- Quality: classification tasks (5 verdicts) — open-weights models match closed for this. Routing only the safety classifier preserves quality where it matters (persona replies stay on GPT-5/Sonnet).

How: add Groq as a model entry in LiteLLM, update `LiteLLM model routing rules` in CLAUDE.md §7.2 to route `quarrel-safety` (new name) to Groq, and update workers `services/safety.py` to call `quarrel-safety` instead of `quarrel-cheap`.

### Default persona to Sonnet 4.6 instead of GPT-5
- GPT-5: ~$1.25/1M input, $10/1M output
- Sonnet 4.6: ~$3/1M input, $15/1M output
- Wait — Sonnet is MORE expensive per token. BUT GPT-5's reasoning tokens (invisible, billed at output rate) often 2-3x the actual output. Net cost often favors Sonnet for argue-mode.
- **Recommended:** A/B test for 1 week, measure cost per resolved chat. Pick winner.
- Risk: Sonnet's voice differs from GPT-5. Persona system prompts may need light tweaks.

### Prompt caching (free, biggest single win)
- Anthropic native + OpenAI prompt caching: 90% discount on cached input tokens
- Anti-sycophant base prompt (~800 tokens) + persona overlay (~400 tokens) + 25 user facts (~600 tokens) = ~1800 tokens that repeat every turn
- Cache TTL: 1 hour for system+persona, 5 min for user facts
- **Savings: ~$80/mo at 15M tokens**
- Already in CLAUDE.md §7.6 — just need to flip on. Verify with Langfuse `cached_tokens` metric.

### Batch API for contradiction nightly job
- Contradiction batch processes ~10k fact-pair comparisons per night
- OpenAI Batch API: 50% off, 24-hour SLA — fine for nightly
- **Savings: ~$40/mo**
- Migrate `apps/workers/jobs/contradiction_batch.py` to use Batch API (already noted as a TODO in §27).

## 2. Self-host stack (already in §3 as deferred)

Things flagged as "switch when scale" in CLAUDE.md §3:

| Service | Cloud cost | Self-host cost | Trigger |
|---|---|---|---|
| Sentry Cloud | $26/mo at 100k events | $0 + Coolify slot | >5k events/mo |
| Resend | $20/mo at 50k emails | $0 + Listmonk on droplet | >100/day |
| LiteLLM Cloud | $99/mo | $0 — already self-hosted ✓ | Done |
| Langfuse Cloud | $59/mo | $0 — already self-hosted ✓ | Done |
| Umami Cloud | $20/mo | $0 — already self-hosted ✓ | Done |

These are already the right call per §3. No action needed until usage triggers the swap.

## 3. Vector + embeddings

- Current: OpenAI text-embedding-3-small ($0.02/1M tokens)
- Alternatives:
  - **BGE-large via Cohere/Together** — $0.01/1M, slightly better recall in our benchmarks
  - **Self-hosted via vLLM** — $0 cost but $$ GPU. Not worth it < 100M tokens/mo
- **Savings: ~$5/mo at our scale.** Skip — not worth the integration cost.

## 4. Database + infra

- Supabase Free: 500MB DB + 1GB storage + 50k MAU. We won't hit until ~5k DAU.
- DigitalOcean droplet: $48/mo fixed. Already optimized.
- DO Spaces backups: $5/mo. Already minimal.

**No action needed** pre-launch.

## 5. Payments

Polar.sh: 4% + $0.40 per transaction. BD-compatible MoR — no swap available.
RevenueCat: free tier for first $2.5k/mo MRR; 1% above. Fine.

**Skip optimization here** until MRR > $10k/mo (then negotiate with Polar).

## 6. Reranking — only if Phase 2 launches

We don't currently rerank vector retrievals. If we add it post-launch:
- Cohere Rerank: $1/1k requests
- **Cohere Rerank → self-hosted bge-reranker-v2-m3** via TEI on Coolify: $0
- ~$30/mo saved at 30k searches/day

Skip until needed.

## Hard rule

Don't optimize cost before product-market fit. The §28 launch gate is 30% week-1 retention on a 100-user cohort. If that fails, none of this matters. After PMF, work top-to-bottom on this list.

## Decision sequence

1. **Today** (1h): wire Groq for safety + flip prompt caching on. ~$125/mo saved.
2. **After 1k chat turns through GPT-5 baseline**: A/B test Sonnet 4.6 default.
3. **At 5k events/mo**: migrate Sentry → GlitchTip.
4. **At 100 emails/day**: migrate Resend → Listmonk.
5. **At PMF**: revisit the rest with real numbers.
