import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";

import ServerWarmingGate from "./components/ServerWarmingGate";
import { FONT_VARIABLES } from "./fonts";
import { AppShell } from "./ui/shell/AppShell";

import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" className={FONT_VARIABLES}>
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
