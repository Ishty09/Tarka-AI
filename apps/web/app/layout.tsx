import type { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import Script from "next/script";
import { hasAcknowledgedCookieNotice } from "@/lib/cookie-notice";
import { CookieBanner } from "./_components/CookieBanner";
import { ThemeProvider } from "./_components/ThemeProvider";
import "./globals.css";

// chore: empty-trigger 2026-05-29 to test Vercel webhook
const UMAMI_WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;
const UMAMI_SCRIPT_URL = process.env.NEXT_PUBLIC_UMAMI_SCRIPT_URL;

export const metadata: Metadata = {
  title: "Quarrel AI",
  description: "The AI that won't let you lie to yourself.",
};

// Mobile rendering — without explicit width=device-width Safari/Chrome
// scale the page to ~980px and shrink, making everything tiny. Allow
// pinch-zoom up to 5× for accessibility. `viewport-fit=cover` lets us
// pad against the iOS notch / home indicator via env(safe-area-inset-*).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

// RTL locales need dir="rtl" on <html> so layout, scrollbars, and form
// controls flip. Keep in sync with LOCALES in packages/shared/constants.
const RTL_LOCALES = new Set(["ar", "he"]);

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const [locale, messages, cookieAcknowledged] = await Promise.all([
    getLocale(),
    getMessages(),
    hasAcknowledgedCookieNotice(),
  ]);
  const dir = RTL_LOCALES.has(locale) ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={dir} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        {UMAMI_WEBSITE_ID && UMAMI_SCRIPT_URL ? (
          <Script
            src={UMAMI_SCRIPT_URL}
            data-website-id={UMAMI_WEBSITE_ID}
            strategy="afterInteractive"
            defer
          />
        ) : null}
        <ThemeProvider>
          <NextIntlClientProvider locale={locale} messages={messages}>
            {children}
            <CookieBanner show={!cookieAcknowledged} locale={locale} />
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
