import { Geist, Geist_Mono } from "next/font/google";

import NavShell from "./components/NavShell";
import ServerWarmingBanner from "./components/ServerWarmingBanner";

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
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ServerWarmingBanner />
        <NavShell>{children}</NavShell>
      </body>
    </html>
  );
}
