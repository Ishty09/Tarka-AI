import type { LocalisedContent } from "../types";

// Privacy Policy — first-draft. Pending lawyer review for US + EU per §28.
//
// Substantive requirements pulled from CLAUDE.md §16:
//   - Controller identity + Bangladesh address
//   - EU representative placeholder (engaged post 10K EU users)
//   - Lawful bases per processing purpose
//   - Recipients / subprocessors with locations (§3)
//   - Retention periods per data type
//   - User rights enumeration
//   - DPO contact
//   - Complaint procedure
//
// Wherever a fact would change at incorporation (street address, DPO name,
// EU rep, supervisory authority for the user's region), we use a clearly
// labelled placeholder so the lawyer pass can fill them in without
// touching the structure.

const en = `# Privacy Policy

This Privacy Policy explains how Quarrel AI ("Quarrel", "we", "us") collects, uses, and shares personal data when you use our website, mobile applications, and related services (collectively, the "Service"). Quarrel is an AI companion designed to disagree with you, push back on your reasoning, and remember your stated positions over time. That product purpose shapes the data we keep and why.

We aim to keep this policy honest and specific. If anything below is unclear, write to **privacy@quarrel.ai** and we will explain it in plain language.

## 1. Who we are

Quarrel AI is operated by the entity listed below ("Controller"). Until incorporation completes the Controller is the founder, Rabbi H, acting in personal capacity.

- Controller: Quarrel AI (entity name pending incorporation)
- Postal address: Dhaka, Bangladesh (street address to be added at incorporation)
- Primary contact: **privacy@quarrel.ai**
- Data Protection contact: **dpo@quarrel.ai**

If you are in the European Economic Area (EEA), the United Kingdom, or Switzerland and our user count in your region reaches the thresholds requiring it, we will appoint an EU representative under Article 27 GDPR and publish their contact details here. Until then, you may use the EU rep contact form linked from this page or write directly to **privacy@quarrel.ai**.

## 2. What we collect and why

We collect only what the Service needs to function and to meet legal obligations. The table below ties each category to a purpose and a lawful basis under Article 6 GDPR. For users in jurisdictions with similar regimes (UK GDPR, Brazil LGPD, California CPRA, etc.) the equivalent basis applies.

### 2.1 Account data
- Email address, username, display name, avatar URL, locale, country, timezone.
- Authentication identifiers (Supabase Auth user ID, Google / Apple Sign-In subject when used).
- Purpose: account creation, login, basic personalisation.
- Lawful basis: performance of a contract (Art. 6(1)(b)).

### 2.2 Age-related data
- Age range you declare during onboarding (under 16 / 16-17 / 18+).
- Method used to assess age (self-declaration, Apple Age API, etc.).
- Purpose: enforcing the under-16 gating described in our Terms.
- Lawful basis: legitimate interests in age-safety (Art. 6(1)(f)); legal obligation where local law requires age gating (Art. 6(1)(c)).

### 2.3 Conversation content
- Messages you send to Quarrel and the model responses you receive, persisted under your account.
- A redacted copy of each message after our safety screen removes phone numbers, email addresses, government IDs, full card numbers, and exact street addresses; embeddings used for memory retrieval are computed from the redacted version only.
- Persona selections, mode (argue / roast / mediate / etc.), and conversation metadata (titles, archive state).
- Purpose: providing the chat product; surfacing contradictions over time; safety review.
- Lawful basis: performance of a contract (Art. 6(1)(b)); legitimate interests for safety review (Art. 6(1)(f)).

### 2.4 Memory and contradiction tracking
- Facts our system extracts from your messages (beliefs, goals, preferences, commitments, rationalisations) and contradiction pairs derived from them.
- Weekly Mirror Reports and quarterly Eulogy summaries generated about your behaviour.
- Purpose: the core "remember every contradiction" feature of the Service.
- Lawful basis: performance of a contract (Art. 6(1)(b)). You may delete any extracted fact at any time from your settings, which prevents its use in future responses.

### 2.5 Social features
- Couples-link records (partner identifiers, consent flags, cross-fact-retrieval flag).
- Group room membership.
- Roast Feed posts you publish, your votes, and moderation outcomes.
- Purpose: enabling the social features you opt into.
- Lawful basis: performance of a contract (Art. 6(1)(b)); explicit consent for cross-partner fact retrieval (Art. 9 / Art. 6(1)(a)).

### 2.6 Commitments and payments
- Wagers, anti-charity selections, check-ins, streak data.
- Subscription tier, billing period, payment status, external subscription IDs from our merchant of record (Polar.sh).
- We do **not** store full payment card numbers. Card data is handled by Polar / Stripe under their own controllership.
- Purpose: running the commitment feature and your subscription.
- Lawful basis: performance of a contract (Art. 6(1)(b)); legal obligation for billing records (Art. 6(1)(c)).

### 2.7 Device and usage data
- IP address (truncated for analytics), user-agent, push subscription tokens, locale headers.
- Aggregated usage events (per §20 analytics event list) captured by our self-hosted analytics.
- Purpose: rate limiting, fraud prevention, product analytics.
- Lawful basis: legitimate interests (Art. 6(1)(f)). Our analytics tool is cookieless and does not assign persistent visitor identifiers.

### 2.8 Safety and moderation
- Records of safety screen verdicts (crisis / abuse / minor self-sexualisation / jailbreak), moderation decisions, and audit log entries for sensitive actions.
- Purpose: protecting users and meeting our legal obligations.
- Lawful basis: legitimate interests in safety (Art. 6(1)(f)); legal obligation under applicable child-safety laws (Art. 6(1)(c)).

### 2.9 Special-category data
Some conversations will contain data that is "special category" under Art. 9 GDPR (health, sexuality, beliefs, etc.). We do not solicit this data and we do not use it for profiling or advertising. Where it appears, we rely on Art. 9(2)(a) (explicit consent — by sending the message you have asked us to process it) or Art. 9(2)(e) (data manifestly made public, where applicable to the Roast Feed). You may delete any such message at any time.

## 3. How long we keep it

- Account profile: while your account is active, plus 30 days after deletion request to permit recovery, then hard-deleted. Audit log entries for the deletion itself are retained for 12 months.
- Conversation messages, facts, contradictions, mirror reports, eulogy reports: until you delete them, or 30 days after account deletion request.
- Roast Feed posts: until you delete them; the public copy may be cached by third parties (search engines, social shares) and we cannot recall it from those caches.
- Safety incident records: 24 months after the incident, longer where legally required.
- Billing records: 7 years where required by applicable tax law.
- Push subscription tokens: until you log out the device or the token expires at the push provider.
- Backups: rolling 30-day backup retention; deleted records persist in backups for at most 30 days before being overwritten.

## 4. Who we share it with

We do not sell your personal data. We share it with the following categories of recipients ("subprocessors") only to the extent needed to operate the Service:

- **Supabase Inc.** (United States) — managed Postgres database, authentication, file storage.
- **OpenAI, L.L.C.** (United States) — primary LLM provider for chat responses and fact extraction. Quarrel has opted out of OpenAI training on our API data.
- **Anthropic, PBC** (United States) — fallback LLM provider on the same opt-out basis.
- **Polar Software, Inc.** (United States) — merchant of record for web subscriptions and one-off charges. Polar processes your name, billing email, and payment instrument data as an independent controller for tax compliance.
- **Resend, Inc.** (United States) — transactional email delivery.
- **Functional Software, Inc. dba Sentry** (United States / Germany) — error monitoring; we configure Sentry to strip personal data from error payloads before transmission.
- **DigitalOcean, L.L.C.** (United States) — virtual machine hosting for our self-hosted services (LiteLLM proxy, Langfuse, Umami analytics).
- **Cloudflare, Inc.** (United States / global) — DNS, CDN, DDoS protection.

The following services are self-hosted by Quarrel on infrastructure listed above; data does not leave our control beyond what is described in this Policy:

- **LiteLLM proxy** — gateway in front of OpenAI and Anthropic; routes requests, applies caching, and writes traces to Langfuse.
- **Langfuse** — LLM-call tracing and evaluation. Stores the model input and output for each call, tied to your hashed user ID for debugging and quality work.
- **Umami** — product analytics, cookieless and self-hosted.

A live list of subprocessors is maintained at our public DPA URL. Material changes will be announced at least 30 days in advance by email to account holders.

## 5. International transfers

Quarrel operates from Bangladesh and routes data to subprocessors located primarily in the United States and the European Union. Where data is transferred outside the EEA, UK, or Switzerland, we rely on the European Commission's Standard Contractual Clauses (2021) supplemented by transfer impact assessments, and on equivalent contractual safeguards for transfers from other jurisdictions. You may request a copy of the relevant clauses by writing to **privacy@quarrel.ai**.

## 6. Your rights

Subject to your local law, you have the following rights:

- **Access** — request a copy of the personal data we hold about you.
- **Rectification** — correct inaccurate or incomplete data.
- **Erasure** — request deletion of your data (subject to legal-hold exceptions).
- **Portability** — receive your data in a machine-readable format (we provide a JSON export from \`/settings/data\`).
- **Restriction** — ask us to limit processing while a dispute is resolved.
- **Objection** — object to processing based on legitimate interests; we will weigh the objection and stop where there is no overriding reason.
- **Withdraw consent** — where processing relies on consent (couples cross-fact retrieval, marketing emails), you may withdraw at any time without affecting prior lawful processing.
- **Automated decision-making** — we do not make decisions producing legal effects about you solely by automated means. Safety screen verdicts that may suspend an account are subject to human review on appeal.

To exercise any right, use the controls under \`/settings/data\` or write to **privacy@quarrel.ai**. We respond within 30 days; complex requests may extend to 90 days with notice.

## 7. Children

Quarrel is not directed at children under 13. We require users to confirm their age range during onboarding. Users who indicate they are under 16 have couples mode, wagers, the Roast Feed, and the persona marketplace disabled. If we learn that we have collected data from a child below the applicable minimum age without verifiable parental consent, we will delete that data promptly.

## 8. Security

We maintain administrative and technical safeguards proportionate to the data we hold, including row-level security on every Supabase table, scoped service-role keys, HMAC-verified webhooks, encrypted backups, and quarterly secret rotation. No system is perfectly secure; if we become aware of a breach affecting your data we will notify you in accordance with applicable law.

## 9. Complaints

If you believe we have mishandled your data you can complain to your local supervisory authority. EU users: a list is maintained at edpb.europa.eu/about-edpb/about-edpb/members_en. UK users: ico.org.uk. We prefer to resolve issues directly — please write to **privacy@quarrel.ai** first.

## 10. Changes to this policy

We will update this policy when our practices, subprocessors, or legal obligations change. Material changes will be announced at least 30 days in advance by email. The "Last updated" date at the top reflects the most recent change.
`;

export const privacy: LocalisedContent = {
  en: {
    title: "Privacy Policy",
    lastUpdated: "2026-05-21",
    summary:
      "How Quarrel AI collects, uses, and shares personal data, with subprocessor list, retention periods, and your GDPR-equivalent rights.",
    markdown: en,
  },
  bn: null,
  hi: null,
  es: null,
  pt: null,
  ar: null,
};
