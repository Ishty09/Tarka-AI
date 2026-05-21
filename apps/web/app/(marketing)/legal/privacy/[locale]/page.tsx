import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isSupportedLocale } from "@/i18n/routing";
import { LEGAL_LOCALES, resolveDocument } from "@/lib/legal";
import { LegalDocument } from "../../_components/LegalDocument";

interface PageProps {
  params: Promise<{ locale: string }>;
}

// Pre-render the launch six; any other supported Locale falls back to
// English at request time (and we still render with a banner).
export function generateStaticParams(): Array<{ locale: string }> {
  return LEGAL_LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) return { title: "Not found" };
  const resolved = resolveDocument("privacy", locale);
  if (!resolved) return { title: "Not found" };
  return {
    title: `${resolved.content.title} | Quarrel`,
    description: resolved.content.summary,
  };
}

export default async function PrivacyLocalePage({ params }: PageProps) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const resolved = resolveDocument("privacy", locale);
  if (!resolved) notFound();
  return <LegalDocument resolved={resolved} />;
}
