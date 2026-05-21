import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { hasAcknowledgedCookieNotice } from "@/lib/cookie-notice";
import { CookieBanner } from "./_components/CookieBanner";
import "./globals.css";

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
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
          <CookieBanner show={!cookieAcknowledged} locale={locale} />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
