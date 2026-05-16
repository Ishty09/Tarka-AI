import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quarrel AI",
  description: "The AI that won't let you lie to yourself.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
