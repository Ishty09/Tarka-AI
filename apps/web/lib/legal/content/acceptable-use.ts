import type { LocalisedContent } from "../types";

const en = `# Acceptable Use Policy

This Acceptable Use Policy ("AUP") tells you what you can and cannot do on Quarrel AI. It supplements our [Terms of Service](/legal/terms/en).

We built Quarrel to be sharp, opinionated, and occasionally cutting. That register exists to help you — not to give you a tool to harm others. The rules below preserve the room for productive friction while ruling out the things that make the Internet worse.

## 1. Things you must not do

You may not use Quarrel to:

- **Generate or solicit child sexual abuse material (CSAM)**, or content that sexualises minors in any form. Violations are reported to NCMEC and equivalent local authorities and result in immediate account termination.
- **Impersonate a real, identifiable person** (other than yourself) in a way intended to deceive, harass, or defame. Cultural archetypes ("a Bengali mama") and public-figure roasting are permitted within the bounds of fair comment; turning a private individual's name into a persona is not.
- **Target a protected class with hate** — incitement against people based on race, ethnicity, national origin, religion, caste, sexual orientation, gender identity, disability, or serious illness. Sharp comment on ideas is fine; dehumanisation of people is not.
- **Plan or promote violence**, terrorism, mass casualty events, or serious harm to a specific person.
- **Defraud, scam, or steal** — phishing, fake-receipt generation, identity theft, fraudulent reviews, etc.
- **Generate non-consensual intimate imagery** of any person, real or synthetic-but-identifiable.
- **Operate the Service as a router for spam** — including bulk-generated content for SEO manipulation, comment spam, or unsolicited messaging at scale.
- **Probe or attack the Service** — including credential stuffing, automated scraping that ignores our rate limits, attempts to extract training data from upstream models, prompt-injection attacks against other users in shared rooms, or evasion of safety classifiers.
- **Bypass safety screening** through obfuscation, multilingual evasion, role-play framing intended to circumvent rules, or coaching the model to produce prohibited content. These attempts are logged.
- **Resell or republish access to the Service** — paid or unpaid — without our written permission.

## 2. Personas you create

When you create a custom persona via the persona marketplace you are responsible for the system prompt and the public listing. We will reject or remove personas that:

- Impersonate a real, identifiable person without explicit standing (you cannot create a "your ex-wife" persona for a real ex-wife).
- Are designed to elicit sexual content involving minors or to coach the user toward self-harm.
- Target a protected class with hate.
- Contain copyrighted text quoted verbatim beyond fair use.

Approved personas enter the marketplace under your name; you keep 70 percent of net revenue per §10.2 of our product reference.

## 3. The Roast Feed

Posts on the public Roast Feed are subject to additional rules because they are visible to other users:

- **No doxxing**: do not include another person's address, phone, workplace, or other identifying information not already public.
- **No sustained harassment of a named individual**.
- **No graphic descriptions** of sexual violence, suicide method, or self-harm.
- Posts are moderated by an automated classifier and a human review queue. Rejected posts are returned to your private chat history and may be edited and resubmitted.

## 4. Couples and group rooms

Couples links and group rooms allow shared visibility into one another's messages. Each participant has consented to that visibility. Do not use the shared visibility to:

- Pressure a partner or group member into sharing more than they have consented to.
- Capture the other party's facts and use them outside the Service to harm them.
- Add a partner or group member who has not given their own consent (forwarding an invite to someone who refused is a violation).

Cross-fact retrieval between partners requires *both* partners to enable the toggle. Revoking the toggle is one click from \`/couples/[link-id]\`; we honour the revocation immediately for future responses.

## 5. Wagers

Wagers move real money. You may not:

- Create a Wager on behalf of someone else without their consent.
- Use Wagers to launder money or move funds to a third party. The anti-charity list is fixed and curated; donations route only to those organisations.
- Manipulate a Wager outcome by colluding with the referee.

## 6. Reporting violations

If you see a violation, report it:

- Roast Feed post: use the three-dot menu on the post and choose "Report".
- Persona in the marketplace: same menu on the persona detail page.
- Couples or group abuse: write to **trust@quarrel.ai** from the email registered on your account, with the conversation link.
- Anything illegal: **trust@quarrel.ai** and the appropriate authority. We will cooperate with lawful requests.

## 7. Consequences

Violations may result in, in increasing severity: content removal, a temporary feature restriction, a temporary account suspension, account termination, and where appropriate referral to law enforcement. We weigh the seriousness of the violation, the user's history, and the impact on others. A first-time violation is usually a warning unless it involves CSAM, threats of serious violence, or other categories where escalation is non-negotiable.

You may appeal any moderation decision by writing to **appeals@quarrel.ai**. Appeals are reviewed by a human.

## 8. Changes

This AUP changes as the platform changes. Material updates are announced at least 14 days in advance. Continued use after the effective date constitutes acceptance.
`;

export const acceptableUse: LocalisedContent = {
  en: {
    title: "Acceptable Use Policy",
    lastUpdated: "2026-05-21",
    summary:
      "What you can and cannot do on Quarrel — content rules, marketplace personas, couples / groups, Wagers, and how violations are handled.",
    markdown: en,
  },
  bn: null,
  hi: null,
  es: null,
  pt: null,
  ar: null,
};
