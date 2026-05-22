// 8 questions per CLAUDE.md §17. Each item is a native <details> — no JS,
// keyboard-accessible, expands cleanly with prefers-reduced-motion.

const QA = [
  {
    q: "Is this safe?",
    a:
      "Every inbound message runs through a safety classifier before the main " +
      "model sees it. Crisis signals pause the chat and surface locale-specific " +
      "hotlines; minor-safety violations terminate the account; jailbreak attempts " +
      "are logged. Full details at /legal/ai-disclosure/en.",
  },
  {
    q: "Is this just ChatGPT with a prompt?",
    a:
      "No. We route through LiteLLM with OpenAI primary and Anthropic fallback, " +
      "wrap every turn with persistent contradiction memory tied to your account, " +
      "and run a separate safety classifier per message. The system prompt is one " +
      "ingredient — not the product.",
  },
  {
    q: "What if I'm in crisis?",
    a:
      "Stop using Quarrel and contact your local emergency services. If you've set " +
      "an emergency contact in /settings/safety, we'll email them after two crisis " +
      "signals in 24 hours. We can't substitute for a human or a crisis line.",
  },
  {
    q: "How is my data used?",
    a:
      "Stored in Supabase, scoped by row-level security to your account. Routed " +
      "to OpenAI and Anthropic with training opt-out on. Never sold. Full table of " +
      "subprocessors at /legal/privacy/en.",
  },
  {
    q: "Can I cancel?",
    a:
      "Any time, in one click from /settings/billing. The current billing period " +
      "stays active until it ends. First payment is refundable for 14 days.",
  },
  {
    q: "Why anti-charities for wagers?",
    a:
      "Stakes only work when losing them actually stings. Donating to a charity " +
      "you ideologically oppose makes the cost real. You type the charity's name " +
      "to confirm — there's no one-click path to losing the stake.",
  },
  {
    q: "What's the difference between Pro and Max?",
    a:
      "Volume. Pro is 200 messages a day, one couple link, 1-year memory depth, " +
      "128K context. Max is 1,500 messages a day, three couple links, forever " +
      "memory, 1M context. Every feature is on every tier.",
  },
  {
    q: "Where are you based?",
    a:
      "Quarrel AI is operated from Dhaka, Bangladesh. Web payments are handled " +
      "by Polar.sh (Merchant of Record). Data residency details and the EU " +
      "representative path are in /legal/privacy/en.",
  },
];

export function FAQ() {
  return (
    <section className="border-b">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
          Frequently asked.
        </h2>
        <ul className="mt-10 flex flex-col gap-3">
          {QA.map((item) => (
            <li key={item.q}>
              <details className="group rounded-lg border bg-card p-5">
                <summary className="flex cursor-pointer items-center justify-between text-base font-medium [&::-webkit-details-marker]:hidden">
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
      </div>
    </section>
  );
}
