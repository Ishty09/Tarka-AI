// Four pillars (CLAUDE.md §17 / §2). One per: Argue, Roast, Mediate, Remember.

const PILLARS = [
  {
    title: "Argue",
    tagline: "Push back, every turn.",
    items: [
      "Devil's Advocate mode runs the strongest counter to your position.",
      "Multi-Agent Council — five voices + a judge — for hard decisions.",
      "Steelman generator strengthens the position you don't want to defend.",
    ],
    link: { label: "See the argue tools", href: "/tools/council" as const },
  },
  {
    title: "Roast",
    tagline: "Sharp, never cruel.",
    items: [
      "Daily Roast — one personalised line at the time you set.",
      "Roast My X — 20 targets including LinkedIn, resumes, dating profiles.",
      "25 cultural personas: Bengali Mama, British Boomer Dad, Mexican Abuela.",
    ],
    link: { label: "See the roast tools", href: "/personas" as const },
  },
  {
    title: "Mediate",
    tagline: "Hold both people honest.",
    items: [
      "Couples mode with triple opt-in cross-fact retrieval.",
      "Group rooms — up to 15 seats with an AI mediator.",
      "Breakup Analyzer reads a thread and tells you what's actually happening.",
    ],
    link: { label: "See the mediate tools", href: "/couples" as const },
  },
  {
    title: "Remember",
    tagline: "Every contradiction. Every dodge.",
    items: [
      "Contradiction Wall — what you said two weeks ago vs today.",
      "Mirror Mode weekly: the patterns you don't see.",
      "Eulogy Test quarterly: 300 words from an honest friend.",
    ],
    link: { label: "See your memory", href: "/contradictions" as const },
  },
];

export function Pillars() {
  return (
    <section className="border-b">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Four ways to use the friend who tells the truth.
          </h2>
          <p className="mt-4 text-sm text-muted-foreground md:text-base">
            All four are on every tier. Only usage limits differ.
          </p>
        </div>
        <ul className="mt-12 grid gap-6 md:grid-cols-2">
          {PILLARS.map((p) => (
            <li
              key={p.title}
              className="flex flex-col gap-4 rounded-xl border bg-card p-6 shadow-sm"
            >
              <div>
                <h3 className="text-xl font-semibold">{p.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{p.tagline}</p>
              </div>
              <ul className="flex flex-col gap-2 text-sm">
                {p.items.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-1 size-1.5 shrink-0 rounded-full bg-foreground/40" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <a
                href={p.link.href}
                className="mt-auto text-sm font-medium underline underline-offset-2"
              >
                {p.link.label} →
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
