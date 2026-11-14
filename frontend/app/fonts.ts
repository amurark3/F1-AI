import { Barlow_Condensed, Geist, Geist_Mono } from "next/font/google";

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

/**
 * The three faces' CSS variables, for the `<html>` of the root layout and of
 * `global-error`, which replaces that layout and so must load the faces
 * itself. Declared once, so each face is hosted once.
 */
export const FONT_VARIABLES = `${geistSans.variable} ${geistMono.variable} ${barlowCondensed.variable}`;
