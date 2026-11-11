import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { Barlow_Condensed, Geist, Geist_Mono } from "next/font/google";

import ServerWarmingGate from "./components/ServerWarmingGate";
import { AppShell } from "./ui/shell/AppShell";

import type { Metadata } from "next";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/** Display face for page titles and section heads (`--font-display` in globals.css). */
const barlowCondensed = Barlow_Condensed({
  variable: "--font-barlow",
  weight: ["600", "700", "800"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "F1 AI",
  description: "F1 AI — Your AI Race Engineer",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // The font variables sit on <html> so :root-level tokens that read them resolve.
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${barlowCondensed.variable}`}>
      <body className="antialiased">
        <ServerWarmingGate>
          <AppShell>{children}</AppShell>
        </ServerWarmingGate>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
