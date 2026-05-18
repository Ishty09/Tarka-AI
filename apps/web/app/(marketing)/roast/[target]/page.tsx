import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ROAST_TARGETS } from "@quarrel/shared/constants";
import { allRoastTargets, getRoastTargetContent } from "@/lib/roast-targets";
import { createServerSupabase } from "@/lib/supabase/server";
import { env } from "@/lib/env";
import { RoastInput } from "./RoastInput";

// Programmatic SEO landing page for each /roast/[target] (§9.2.2).
//
// generateStaticParams returns all 20 target slugs so Next pre-renders
// them at build time. generateMetadata + JSON-LD give Google rich-result
// material per target.

interface PageProps {
  params: Promise<{ target: string }>;
}

export function generateStaticParams(): Array<{ target: string }> {
  return ROAST_TARGETS.map((target) => ({ target }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { target } = await params;
  const content = getRoastTargetContent(target);
  if (!content) {
    return { title: "Not found" };
  }
  const title = `Roast My ${content.title} | Quarrel AI`;
  const description = `Get your ${content.title.toLowerCase()} brutally critiqued by an anti-sycophant AI in seconds. ${content.subhead}`;
  const url = new URL(`/roast/${target}`, env.NEXT_PUBLIC_APP_URL).toString();
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title,
      description,
      url,
      type: "website",
      siteName: "Quarrel AI",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function RoastTargetPage({ params }: PageProps) {
  const { target } = await params;
  const content = getRoastTargetContent(target);
  if (!content) notFound();

  // Authenticated? affects the CTA copy and which surface the form posts to.
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  const isAuthed = !!user;

  const appUrl = env.NEXT_PUBLIC_APP_URL;
  const url = new URL(`/roast/${target}`, appUrl).toString();

  // JSON-LD for SoftwareApplication + FAQPage. Google rich results.
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: `Roast My ${content.title}`,
      description: content.subhead,
      url,
      applicationCategory: "ProductivityApplication",
      operatingSystem: "Web",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      publisher: { "@type": "Organization", name: "Quarrel AI", url: appUrl },
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: content.faq.map((f) => ({
        "@type": "Question",
        name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    },
  ];

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <header className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Quarrel · Roast My X
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Roast My {content.title}
        </h1>
        <p className="text-base text-muted-foreground">{content.subhead}</p>
      </header>

      <section className="mt-8">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What you&apos;ll get
        </h2>
        <ul className="mt-3 flex flex-col gap-3">
          {content.examples.map((ex, i) => (
            <li
              key={i}
              className="rounded-md border border-input bg-muted/30 px-4 py-3 text-sm leading-relaxed"
            >
              &quot;{ex}&quot;
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Get yours
        </h2>
        <div className="mt-3">
          <RoastInput
            target={content.slug}
            label={content.input_label}
            placeholder={content.input_placeholder}
            authed={isAuthed}
          />
        </div>
      </section>

      <section className="mt-12">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          FAQ
        </h2>
        <dl className="mt-3 flex flex-col gap-4">
          {content.faq.map((f, i) => (
            <div key={i} className="rounded-md border border-input bg-background p-4 shadow-sm">
              <dt className="text-sm font-semibold">{f.q}</dt>
              <dd className="mt-1 text-sm text-muted-foreground">{f.a}</dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="mt-12 flex flex-col gap-3 border-t pt-6 text-xs text-muted-foreground">
        <p>
          Quarrel is the AI built to disagree, push back, and refuse to flatter.{" "}
          <Link href="/" className="underline">Read more</Link>.
        </p>
        <nav className="flex flex-wrap gap-2">
          {allRoastTargets()
            .filter((t) => t.slug !== content.slug)
            .slice(0, 8)
            .map((t) => (
              <Link
                key={t.slug}
                href={`/roast/${t.slug}`}
                className="rounded-full border border-input bg-background px-3 py-1 hover:bg-accent"
              >
                Roast My {t.title}
              </Link>
            ))}
        </nav>
      </footer>
    </main>
  );
}
