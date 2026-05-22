// Pricing-focused FAQ for /pricing (CLAUDE.md §18). Different lens than
// the landing FAQ: this one only answers money / limits / refund
// questions a buyer asks before clicking checkout.

const QA = [
  {
    q: "Do annual plans really save 30%?",
    a:
      "Yes. Pro annual is $79 instead of $9.99 × 12 = $119.88 — that's $40.88 " +
      "saved, ~34%. Max annual is $199 instead of $24.99 × 12 = $299.88 — " +
      "that's $100.88 saved, ~34%.",
  },
  {
    q: "What happens when I hit my message limit?",
    a:
      "The next message returns a 429 with an upgrade prompt. The conversation " +
      "isn't deleted — pick up the next day when the daily counter resets at " +
      "00:00 UTC, or upgrade to keep going. Free → Pro upgrade applies the new " +
      "daily limit immediately.",
  },
  {
    q: "Can I downgrade?",
    a:
      "Yes, any time. The downgrade takes effect at the next renewal, so you " +
      "keep paid features until the current period ends. If you downgrade to " +
      "Free, your data stays — only the limits drop.",
  },
  {
    q: "How does the 14-day money-back guarantee work?",
    a:
      "First payment on Pro or Max is refundable within 14 days, provided you " +
      "haven't already used more than the Free tier's daily equivalent during " +
      "that window. Email refunds@quarrel.ai with your account email. After 14 " +
      "days the subscription becomes non-refundable except where local consumer " +
      "law says otherwise.",
  },
  {
    q: "Who handles tax + invoicing?",
    a:
      "Polar.sh is the merchant of record for all web payments. They handle EU " +
      "VAT, US sales tax, and country-level remittance. Invoices are emailed " +
      "after each successful charge and available under Settings → Billing.",
  },
  {
    q: "Can I pay with anything other than card?",
    a:
      "Polar supports cards (Visa / Mastercard / Amex), Apple Pay, Google Pay, " +
      "and SEPA Direct Debit in the EU. Bank transfers are not currently " +
      "supported. Pricing is in USD; Polar converts at checkout.",
  },
];

export function PricingFAQ() {
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
        Pricing questions.
      </h2>
      <ul className="mt-6 flex flex-col gap-3">
        {QA.map((item) => (
          <li key={item.q}>
            <details className="group rounded-lg border bg-card p-5">
              <summary className="flex cursor-pointer items-center justify-between text-sm font-medium [&::-webkit-details-marker]:hidden">
                <span>{item.q}</span>
                <span
                  aria-hidden
                  className="ml-4 inline-flex size-6 shrink-0 items-center justify-center rounded-full border text-sm transition-transform group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {item.a}
              </p>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
