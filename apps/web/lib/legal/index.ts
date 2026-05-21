// Legal-document content registry + resolver (CLAUDE.md §16, §27 step 54).
//
// Each document module exports a LocalisedContent: { en, bn, hi, es, pt, ar }.
// The English entry is required; other locales are filled in as legal-grade
// translations land. Until then `resolveDocument` falls back to English and
// flags it so the page can render a translation-pending banner.

import type { Locale } from "@quarrel/shared/constants";
import { aiDisclosure } from "./content/ai-disclosure";
import { acceptableUse } from "./content/acceptable-use";
import { cookies } from "./content/cookies";
import { dpa } from "./content/dpa";
import { privacy } from "./content/privacy";
import { terms } from "./content/terms";
import {
  LEGAL_DOC_TYPES,
  LEGAL_LOCALES,
  type LegalDocType,
  type LegalLocale,
  type LocalisedContent,
  type ResolvedLegalDocument,
} from "./types";

export {
  LEGAL_DOC_TYPES,
  LEGAL_LOCALES,
  type LegalDocType,
  type LegalLocale,
  type LocalisedContent,
  type ResolvedLegalDocument,
} from "./types";

const REGISTRY: Record<LegalDocType, LocalisedContent> = {
  privacy,
  terms,
  "ai-disclosure": aiDisclosure,
  "acceptable-use": acceptableUse,
  cookies,
  dpa,
};

export function isLegalDocType(value: string): value is LegalDocType {
  return (LEGAL_DOC_TYPES as readonly string[]).includes(value);
}

export function isLegalLocale(value: string): value is LegalLocale {
  return (LEGAL_LOCALES as readonly string[]).includes(value);
}

/** Public face of the registry — used by the legal index page + footer. */
export function getDocumentTitle(type: LegalDocType): string {
  return REGISTRY[type].en?.title ?? type;
}

/** Stable label per document type, for the footer + index card list. */
export const DOCUMENT_LABELS: Record<LegalDocType, string> = {
  privacy: "Privacy Policy",
  terms: "Terms of Service",
  "ai-disclosure": "AI Disclosure",
  "acceptable-use": "Acceptable Use",
  cookies: "Cookie Policy",
  dpa: "Data Processing Agreement",
};

export function resolveDocument(
  type: LegalDocType,
  requestedLocale: Locale,
): ResolvedLegalDocument | null {
  const map = REGISTRY[type];
  if (!map) return null;

  // Direct hit when the requested locale is one of our publishing locales
  // AND has localised content. Otherwise fall back to English.
  const candidate = isLegalLocale(requestedLocale) ? map[requestedLocale] : null;
  if (candidate) {
    return {
      type,
      requestedLocale,
      effectiveLocale: requestedLocale as LegalLocale,
      isFallback: false,
      content: candidate,
    };
  }

  const fallback = map.en;
  if (!fallback) {
    // English missing is a registry bug — fail loudly.
    return null;
  }
  return {
    type,
    requestedLocale,
    effectiveLocale: "en",
    isFallback: true,
    content: fallback,
  };
}

/** Every (type, locale) combination — fed to generateStaticParams. */
export function allLegalParams(): Array<{ type: LegalDocType; locale: LegalLocale }> {
  const out: Array<{ type: LegalDocType; locale: LegalLocale }> = [];
  for (const type of LEGAL_DOC_TYPES) {
    for (const locale of LEGAL_LOCALES) {
      out.push({ type, locale });
    }
  }
  return out;
}
