import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import Script from "next/script";
import { hasAcknowledgedCookieNotice } from "@/lib/cookie-notice";
import { CookieBanner } from "./_components/CookieBanner";
import { ThemeProvider } from "./_components/ThemeProvider";
import "./globals.css";

const UMAMI_WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;
const UMAMI_SCRIPT_URL = process.env.NEXT_PUBLIC_UMAMI_SCRIPT_URL;

export const metadata: Metadata = {
  title: "Quarrel AI",
  description: "The AI that won't let you lie to yourself.",
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
