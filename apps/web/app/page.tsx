import type { Metadata } from "next";
import { FAQ } from "./_components/landing/FAQ";
import { Footer } from "./_components/landing/Footer";
import { Hero } from "./_components/landing/Hero";
import { PersonasCarousel } from "./_components/landing/PersonasCarousel";
import { Pillars } from "./_components/landing/Pillars";
import { Pricing } from "./_components/landing/Pricing";
import { Problem } from "./_components/landing/Problem";

export const metadata: Metadata = {
  title: "Quarrel AI — The AI that won't let you lie to yourself.",
  description:
    "Quarrel argues, roasts, mediates relationship and group disputes, and tracks every contradiction. Free tier 15 messages a day. Pro $9.99/mo. Max $24.99/mo.",
  openGraph: {
    type: "website",
    siteName: "Quarrel AI",
    title: "Quarrel AI — The AI that won't let you lie to yourself.",
    description:
      "The first AI companion engineered to disagree with you. Argue, roast, mediate, remember.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Quarrel AI — The AI that won't let you lie to yourself.",
    description:
      "The first AI companion engineered to disagree with you. Argue, roast, mediate, remember.",
  },
};

export default function HomePage() {
  return (
    <>
      <Hero />
      <Problem />
      <Pillars />
      <PersonasCarousel />
      <Pricing />
      <FAQ />
      <Footer />
    </>
  );
}
