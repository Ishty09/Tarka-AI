import Link from "next/link";

// Apex landing hero (CLAUDE.md §17). Above-the-fold copy + CTA + a
// three-message demo conversation. The animation is pure CSS — no client
// component, no JS, no layout shift. Loads under 5KB on the wire.

const DEMO: { from: "user" | "ai"; text: string }[] = [
  {
    from: "user",
    text: "I think I should quit my job to start a YouTube channel.",
  },
  {
    from: "ai",
    text:
      "You said the same thing six months ago. Then you made two videos and stopped. " +
      "What's different this time, other than the boredom?",
  },
  {
    from: "user",
    text: "…",
  },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b">
      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 md:grid-cols-2 md:gap-8 md:py-32">
        <div className="flex flex-col justify-center gap-6">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Quarrel AI
          </p>
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl lg:text-6xl">
            The AI that won&apos;t let you lie to yourself.
          </h1>
          <p className="max-w-xl text-base text-muted-foreground md:text-lg">
            Quarrel argues, roasts, and remembers every contradiction. Stop
            talking to yes-men.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
            >
              Start fighting →
            </Link>
            <Link
              href="/pricing"
              className="inline-flex items-center justify-center rounded-md border border-input px-5 py-3 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
            >
              See pricing
            </Link>
          </div>
          <p className="text-xs text-muted-foreground">
            Free tier · 15 messages a day · No credit card · Cancel anytime.
          </p>
        </div>

        <div
          aria-label="Sample conversation"
          className="relative rounded-2xl border bg-card p-5 shadow-lg"
        >
          <div className="flex items-center gap-2 border-b pb-3 text-xs text-muted-foreground">
            <span className="size-2 rounded-full bg-emerald-500" />
            Devil&apos;s Advocate · Argue mode
          </div>
          <ul className="mt-4 flex flex-col gap-3 text-sm">
            {DEMO.map((m, i) => (
              <li
                key={i}
                className={`hero-demo-message flex ${
                  m.from === "user" ? "justify-end" : "justify-start"
                }`}
                style={{ animationDelay: `${0.3 + i * 0.6}s` }}
              >
                <span
                  className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                    m.from === "user"
                      ? "rounded-br-sm bg-primary text-primary-foreground"
                      : "rounded-bl-sm border bg-background"
                  }`}
                >
                  {m.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
