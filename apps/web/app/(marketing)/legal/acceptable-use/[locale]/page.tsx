import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isSupportedLocale } from "@/i18n/routing";
import { LEGAL_LOCALES, resolveDocument } from "@/lib/legal";
import { LegalDocument } from "../../_components/LegalDocument";

interface PageProps {
  params: Promise<{ locale: string }>;
}

export function generateStaticParams(): Array<{ locale: string }> {
  return LEGAL_LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) return { title: "Not found" };
  const resolved = resolveDocument("acceptable-use", locale);
  if (!resolved) return { title: "Not found" };
  return {
    title: `${resolved.content.title} | Quarrel`,
    description: resolved.content.summary,
  };
}

export default async function AcceptableUseLocalePage({ params }: PageProps) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const resolved = resolveDocument("acceptable-use", locale);
  if (!resolved) notFound();
  return <LegalDocument resolved={resolved} />;
}
