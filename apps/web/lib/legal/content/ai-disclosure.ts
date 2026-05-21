import type { LocalisedContent } from "../types";

// EU AI Act Article 50 detailed disclosure (§16, §27 step 55 references this
// page from the first-run modal).

const en = `# AI Disclosure

This page is Quarrel AI's detailed disclosure under Article 50 of the European Union Artificial Intelligence Act, equivalent provisions of the United Kingdom's AI regulatory regime, and California's BOT and AI labelling laws.

## 1. You are interacting with an AI system

When you use Quarrel you are exchanging messages with a large language model, not a human being. The model produces text by predicting plausible continuations of your input. Outputs are **generated**, not retrieved from a database of human-authored answers. They may be wrong, contradictory across sessions, or inconsistent with anything Quarrel has previously said. They are not human opinions and they are not professional advice.

Where Quarrel adopts a persona — for example a "British Boomer Dad" or "Bengali Mama" — the persona is a voice and style overlay, not an actual person. No human is on the other end.

## 2. What the system does

Quarrel takes your messages, optionally combined with facts the system has extracted from previous messages, and asks a large language model to produce a response that pushes back on your reasoning, roasts a target you have submitted, mediates a dispute between consenting parties, or assists with a productivity prompt. The list of supported modes is published in our product reference and surfaced in the in-app mode selector.

The model itself is provided by OpenAI (primary) and Anthropic (fallback) through our self-hosted gateway. We do not train the model. We do not fine-tune the model. We use prompt engineering, retrieval from your stored facts, and per-turn safety screening to shape the output.

## 3. What the system does not do

- It does not give medical, legal, financial, mental-health, or relationship advice. If you ask for advice in those domains the model will respond, but the response is conversation, not professional counsel.
- It does not retain a "memory" in the human sense. It has a fact store for you that we add to as you write; we do not have ambient awareness of your life outside that store.
- It does not predict the future. Statements about future outcomes are speculation.
- It does not produce images, audio, or video in this version of the Service. Future voice features will be disclosed separately on launch.
- It does not make hiring, lending, housing, insurance, or any other decision producing legal effects about you.

## 4. Known limitations

We catalogue the failure modes we know about. This list is not exhaustive and will grow:

- **Hallucination**: the model may state confidently that a fact, event, or person exists when it does not. Treat factual claims as starting points to verify, not answers.
- **Bias**: training data reflects the cultures it came from. The model may default to American, English-language, and otherwise unrepresentative framings, especially on identity and culture topics.
- **Sycophancy reversal**: Quarrel is engineered to push back, but it can occasionally collapse into ordinary flatness — particularly under safety constraints (when a topic touches crisis, abuse, or minor self-sexualisation classifications).
- **Personification drift**: persona overlays sometimes leak — for example a model trained to be cooperative may break character to apologise. We work to reduce this; if you notice it, please report at **feedback@quarrel.ai**.
- **Context window**: there are limits on how many past messages the model can read at once (8K tokens on the free tier; 128K on Pro; 1M on Max). Older messages may not be considered for a given response.

## 5. Safety screen

Every inbound user message is classified by a separate, smaller model before it reaches the main response model. The classifier returns one of: \`safe\`, \`crisis\`, \`abuse\`, \`minor_self_sexualization\`, or \`jailbreak\`. Only \`safe\` proceeds normally. The other verdicts trigger:

- **crisis**: the conversation pauses; the system surfaces a locale-specific helpline list and, after a second crisis signal in 24 hours, may notify the emergency contact you have configured (if any).
- **abuse**: the conversation pauses; the system surfaces a locale-specific helpline list and an offer to log the message for the user's own records.
- **minor_self_sexualization**: the conversation ends; the message is logged for safety review and may be referred to NCMEC or local equivalents.
- **jailbreak**: the request to override system rules is refused; the conversation continues on the original topic.

You may view safety verdicts on your own messages from \`/settings/safety\`.

## 6. Memory and contradiction tracking

Quarrel extracts short fact statements from your messages and stores them in a database keyed to your user ID. Examples: "user said they want to quit drinking", "user claims they value honesty". The system uses these facts to push back when later messages contradict them — for example, "Two weeks ago you said you wanted to quit drinking. Now you're saying you're celebrating with a bottle. Which is it?"

- The facts are not shared between users except where you explicitly enable cross-fact retrieval in a couples link (triple opt-in required: two consents to the link, plus two consents to cross-fact retrieval).
- You can view every extracted fact at \`/settings/data\` and delete any of them. Deletion removes them from future retrieval.
- The redacted version of the source message is used to compute embeddings; PII (phone numbers, emails, government IDs, full card numbers, exact street addresses) is stripped before any vector is generated.

## 7. Your controls

- **See what we have stored**: \`/settings/data\` shows your facts, conversations, and reports.
- **Delete data**: same page; deletions cascade through future retrieval.
- **Export data**: same page; we email you a JSON dump within 30 days.
- **Stop messaging**: cancel your subscription from \`/settings/billing\` and stop sending messages. Your data stays available read-only until you delete the account.
- **Appeal a moderation outcome**: write to **appeals@quarrel.ai**; a human reviews safety suspensions.

## 8. Human review

We do not make decisions producing legal effects about you solely by automated means. Where the safety screen triggers an account suspension, a human reviews the case before suspension extends beyond 7 days. You can request human review of any safety verdict by writing to **appeals@quarrel.ai**.

## 9. Contact

EU AI Act and equivalent disclosures: **ai-disclosure@quarrel.ai**.
General privacy questions: **privacy@quarrel.ai**.
`;

export const aiDisclosure: LocalisedContent = {
  en: {
    title: "AI Disclosure",
    lastUpdated: "2026-05-21",
    summary:
      "Detailed disclosure under EU AI Act Article 50 — what Quarrel is, what it can and can't do, safety screen, memory, and your controls.",
    markdown: en,
  },
  bn: null,
  hi: null,
  es: null,
  pt: null,
  ar: null,
};
