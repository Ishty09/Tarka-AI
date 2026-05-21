import Link from "next/link";
import {
  DOCUMENT_LABELS,
  LEGAL_DOC_TYPES,
  type ResolvedLegalDocument,
} from "@/lib/legal";
import { Markdown } from "./markdown";

// Shared layout for every /legal/*/[locale] page. Renders the title,
// last-updated, an optional "translation pending" banner when the page
// is falling back to English, the markdown body, and a sibling-doc list.

const LOCALE_LABELS: Record<string, string> = {
  en: "English",
  bn: "বাংলা",
  hi: "हिन्दी",
  es: "Español",
  pt: "Português",
  ar: "العربية",
};

interface Props {
  resolved: ResolvedLegalDocument;
}

export function LegalDocument({ resolved }: Props) {
  const { type, content, isFallback, requestedLocale, effectiveLocale } = resolved;
  const requestedLabel = LOCALE_LABELS[requestedLocale] ?? requestedLocale;

  return (
    <article className="mx-auto w-full max-w-2xl px-6 py-12">
      <nav className="mb-6 text-xs text-muted-foreground">
        <Link href="/legal" className="underline underline-offset-2">
          Legal
        </Link>
        <span className="mx-2">/</span>
        <span>{DOCUMENT_LABELS[type]}</span>
      </nav>

      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{content.title}</h1>
        <p className="mt-2 text-xs uppercase tracking-wide text-muted-foreground">
          Last updated {content.lastUpdated} · Effective locale: {effectiveLocale}
        </p>
      </header>

      {isFallback ? (
        <div
          role="note"
          className="mt-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <strong className="font-semibold">Translation pending.</strong>{" "}
          The {requestedLabel} version of this document has not been published yet.
          The English source is shown below; consult it as the authoritative
          version until the localised text lands.
        </div>
      ) : null}

      <section className="mt-6">
        <Markdown source={content.markdown} />
      </section>

      <footer className="mt-10 border-t pt-6 text-sm">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          Other legal documents
        </p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {LEGAL_DOC_TYPES.filter((other) => other !== type).map((other) => (
            <li key={other}>
              <Link
                href={`/legal/${other}/${effectiveLocale}`}
                className="underline underline-offset-2"
              >
                {DOCUMENT_LABELS[other]}
              </Link>
            </li>
          ))}
        </ul>
      </footer>
    </article>
  );
}
