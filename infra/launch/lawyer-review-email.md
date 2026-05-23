# Lawyer review — email draft + attachment bundle

This is the **§28 launch gate** that takes the longest external dependency.
Send Monday morning so the review window starts immediately.

## Attachment

Generate `legal-bundle.md` (single file with all 6 drafts) from the
`apps/web/lib/legal/content/*.ts` modules:

```bash
node infra/launch/build-legal-bundle.mjs > legal-bundle.md
```

(Script is in this directory; it reads each module's `en.markdown` and
concatenates them with separators + the §16 placeholder notes.)

## Email body (edit before sending)

Subject: **Quarrel AI — pre-launch privacy + ToS review (US + EU)**

> Hi [lawyer name],
>
> I'm Rabbi, the founder of Quarrel AI — an anti-sycophant AI companion
> that argues, roasts, and tracks user contradictions over time. We're
> targeting a public launch in [target month] and I need US + EU
> review on our six legal documents before we go live.
>
> Attached is `legal-bundle.md` (~10K words, all six docs):
>
>   1. Privacy Policy — controller in Bangladesh, subprocessors named,
>      retention table per §16 of our internal spec.
>   2. Terms of Service — subscription via Polar.sh as Merchant of
>      Record, 14-day refund window, arbitration seated in Dhaka.
>   3. AI Disclosure (EU AI Act Article 50) — explicit "you are talking
>      to an AI" disclosure with limitations + safety screen flow.
>   4. Acceptable Use Policy.
>   5. Cookie Policy — minimal because our analytics (Umami) is
>      cookieless.
>   6. Data Processing Agreement (B2B-side, not yet launched but want
>      to land it).
>
> Specific things I want your eyes on:
>
>   - The Bangladesh controller + EU Article 27 representative placeholder.
>     I'd rather appoint an EU rep proactively than wait for the 10K-user
>     trigger. Recommendation?
>   - The "anti-charity" wager mechanism — user stakes money on a goal,
>     loss donates to a charity they ideologically oppose. Real
>     donation, irreversible. Need US + EU consumer-protection sign-off
>     on the typed-confirmation flow.
>   - Cross-fact retrieval in Couples mode — triple opt-in (two consents
>     to the link, plus two cross-fact toggles). Is this enough for
>     Art. 6(1)(a) explicit consent on special-category data?
>   - Crisis flow + emergency contact email — when a user ticks the
>     "alert this person if I'm in crisis" box, we email a third party
>     after two crisis signals in 24h. GDPR position on this?
>   - Minor safety — we age-gate at 16, reject < 13 outright, NCMEC-
>     report any minor_self_sexualization classification. Mandatory
>     reporter status in any jurisdiction?
>
> Quote, timeline, and what you need from me to start are all welcome.
> Happy to do a 30-min call if it'll be faster.
>
> — Rabbi
>
> uprightseo24@gmail.com
> Dhaka, Bangladesh

## What to do with the response

1. **Quote:** record in 1Password under "Lawyer engagement".
2. **Timeline:** if > 4 weeks, find a second lawyer in parallel — don't
   serialize on one external dependency.
3. **Redline:** drop into a branch off `main`, update the matching
   `apps/web/lib/legal/content/*.ts` module, run `pnpm typecheck`,
   commit as `chore(legal): lawyer-review redline for <doc>`.
4. **Sign-off note:** record in `infra/runbooks/post-mortems/` under
   `legal-review-<date>.md` — date, lawyer name, scope, anything left
   open.
