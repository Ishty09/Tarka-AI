// Eight personas with sample roasts (CLAUDE.md §17 — "Personas carousel").
//
// Carousel = horizontal-scroll on mobile, three-column grid past md. CSS
// scroll-snap makes the mobile experience feel native without any JS.

const PERSONAS = [
  {
    slug: "devils_advocate",
    name: "Devil's Advocate",
    register: "EN · clinical, lawyer-like",
    roast:
      "You opened with three caveats before saying anything. If your idea was good, " +
      "you wouldn't need the run-up.",
  },
  {
    slug: "british_boomer_dad",
    name: "British Boomer Dad",
    register: "EN-GB · disappointed father",
    roast:
      "Bit ambitious, isn't it? I'd lower the bar — say, finishing one of these " +
      "projects before announcing the next.",
  },
  {
    slug: "bengali_mama",
    name: "Bengali Mama",
    register: "BN · Dhaka uncle, weaponised sighs",
    roast:
      "Haah… amar shomoy e amra ekhono uthe gechi, ar tui ekhono breakfast e " +
      "Instagram dekhchish. Bhalo. Khub bhalo.",
  },
  {
    slug: "south_indian_uncle",
    name: "South Indian Uncle",
    register: "HI/TA · comparison-driven",
    roast:
      "My friend's son is doing his PhD at IIT Madras. He also wakes up at 5 AM. " +
      "Just sharing. No pressure.",
  },
  {
    slug: "mexican_abuela",
    name: "Mexican Abuela",
    register: "ES-MX · tough love, food guilt",
    roast:
      "Ay, mijo. ¿Tú crees que yo trabajé toda mi vida para que tú duermas hasta " +
      "las once? Come algo. Y arregla tu vida.",
  },
  {
    slug: "italian_nonna",
    name: "Italian Nonna",
    register: "IT · church and the village",
    roast:
      "Mangia. You are too thin. And too sad. Both are because you do not call your " +
      "mother. Make the pasta. Make the call.",
  },
  {
    slug: "korean_tiger_mom",
    name: "Korean Tiger Mom",
    register: "KO · results-only",
    roast:
      "삼촌 sister's daughter just got into SKY. You? You got into 'taking a year off " +
      "to figure things out'. That is not a school.",
  },
  {
    slug: "the_economist",
    name: "The Economist",
    register: "Council member · opportunity cost",
    roast:
      "Expected value of this plan: negative. You priced the upside without " +
      "modelling the year you lose if it fails. Show me the math, not the vibe.",
  },
];

export function PersonasCarousel() {
  return (
    <section className="border-b bg-muted/30">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            25 cultural personas. None of them flatter you.
          </h2>
          <p className="mt-4 text-sm text-muted-foreground md:text-base">
            Eight previews here. The full library covers 16 launch locales.
          </p>
        </div>

        <ul
          className="mt-12 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-4 md:grid md:grid-cols-2 md:gap-6 md:overflow-visible lg:grid-cols-4"
          aria-label="Persona previews"
        >
          {PERSONAS.map((p) => (
            <li
              key={p.slug}
              className="flex min-w-[80%] snap-start flex-col gap-3 rounded-xl border bg-card p-5 shadow-sm md:min-w-0"
            >
              <div>
                <h3 className="text-base font-semibold">{p.name}</h3>
                <p className="text-xs text-muted-foreground">{p.register}</p>
              </div>
              <blockquote className="text-sm leading-relaxed text-muted-foreground">
                &ldquo;{p.roast}&rdquo;
              </blockquote>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
