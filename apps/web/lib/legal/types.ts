// Shared types for legal documents (CLAUDE.md §16, §27 step 54).
//
// The set of document types is closed — adding a new one means adding
// both a content module and a [locale] route, and updating the footer.

import type { Locale } from "@quarrel/shared/constants";

export const LEGAL_DOC_TYPES = [
  "privacy",
  "terms",
  "ai-disclosure",
  "acceptable-use",
  "cookies",
  "dpa",
] as const;

export type LegalDocType = (typeof LEGAL_DOC_TYPES)[number];

/**
 * Locales we publish legal content in. Matches the §27 step 53 launch six.
 * Other LOCALES values are accepted by the route but fall back to English.
 */
export const LEGAL_LOCALES = ["en", "bn", "hi", "es", "pt", "ar"] as const;
export type LegalLocale = (typeof LEGAL_LOCALES)[number];

export interface LegalContent {
  /** Display title shown in the page H1 + <title>. */
  title: string;
  /** Plain ISO-8601 date string. Rendered, not used as a sort key. */
  lastUpdated: string;
  /** One-line summary used in <meta description>. */
  summary: string;
  /** Body content in the restricted markdown subset (see markdown.tsx). */
  markdown: string;
}

/**
 * Per-document, per-locale content map. `null` means "no localised draft
 * yet — render the English source with a translation-pending banner".
 */
export type LocalisedContent = Record<LegalLocale, LegalContent | null>;

export interface ResolvedLegalDocument {
  type: LegalDocType;
  /** Locale the visitor asked for. */
  requestedLocale: Locale;
  /** Locale the rendered content is actually in. */
  effectiveLocale: LegalLocale;
  /** True when the visitor asked for a locale we don't have yet. */
  isFallback: boolean;
  content: LegalContent;
}
