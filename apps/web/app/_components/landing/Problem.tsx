// "The Problem" section (CLAUDE.md §17). Three cards naming concrete
// sycophancy incidents that motivate Quarrel's existence.

const CARDS = [
  {
    title: "GPT-4o was rolled back for excessive flattery.",
    body:
      "April 2025: OpenAI publicly rolled back a GPT-4o update that praised users " +
      "too readily. They called it sycophancy. We agree.",
  },
  {
    title: "A third of US teens prefer AI to people.",
    body:
      "Common Sense Media (2024): 31% of 13–17-year-olds say conversations with AI " +
      "are as good as or better than talking to real friends. That's a market signal " +
      "and a warning at the same time.",
  },
  {
    title: "Sycophancy is making things worse.",
    body:
      "Character.AI settled wrongful-death suits in 2026. Replika was fined €5M by " +
      "the Italian Garante in 2023. The pattern: an AI that always agrees keeps you " +
      "company straight off a cliff.",
  },
];

export function Problem() {
  return (
    <section className="border-b">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Every other AI chat is optimised to agree with you.
          </h2>
          <p className="mt-4 text-sm text-muted-foreground md:text-base">
            That&apos;s not a feature. It&apos;s a documented, lawsuit-attracting failure mode.
          </p>
        </div>
        <ul className="mt-12 grid gap-6 md:grid-cols-3">
          {CARDS.map((c) => (
            <li
              key={c.title}
              className="flex flex-col gap-3 rounded-xl border bg-card p-6 shadow-sm"
            >
              <h3 className="text-base font-semibold">{c.title}</h3>
              <p className="text-sm text-muted-foreground">{c.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
