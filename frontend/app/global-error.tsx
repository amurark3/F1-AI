"use client";

import * as Sentry from "@sentry/nextjs";
import Link from "next/link";
import { useEffect } from "react";

import { FONT_VARIABLES } from "./fonts";
import BrandLockup from "./ui/BrandLockup";
import { PageHero } from "./ui/PageHero";
import { WRAP } from "./ui/shell/wrap";
import "./globals.css";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  /** Refreshes the route and renders it again (Next.js 16.3+). */
  retry: () => void;
}

/** The mockups' `.btn` (`docs/design/redesign/system.css`): display caps on a 48 px button. */
const BUTTON =
  "inline-flex h-12 items-center px-6 font-display text-[19px] font-extrabold uppercase leading-none tracking-[0.02em]";
const PRIMARY = `${BUTTON} bg-f1-red text-rc-ink transition-[filter] hover:brightness-110`;
const GHOST = `${BUTTON} border border-rc-ink/35 text-rc-ink transition-colors hover:border-rc-ink`;

/**
 * The last-resort boundary: an error no route-level boundary caught replaces the
 * whole root layout with this page. React swallows errors a boundary catches,
 * so without this report Sentry would never hear about them.
 *
 * With the layout gone, the page brings its own document, styles and faces,
 * and stays clear of the shell, which may be what failed.
 */
export default function GlobalError({ error, retry }: Readonly<GlobalErrorProps>) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en" className={FONT_VARIABLES}>
      <body className="antialiased">
        <title>Something went wrong · F1 AI</title>
        <header className="border-b border-rc-line">
          <div className={`${WRAP} flex h-15 items-center`}>
            <Link href="/" aria-label="F1 AI home" className="shrink-0">
              <BrandLockup />
            </Link>
          </div>
          <div aria-hidden="true" className="h-0.5 bg-f1-red" />
        </header>
        <main className={`${WRAP} pb-24 pt-16 sm:pt-24`}>
          <PageHero
            eyebrow="Error"
            title="Something went wrong"
            meta="This page hit an error and couldn't load. Try again, or start over from the homepage."
          >
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={retry} className={PRIMARY}>
                Try again
              </button>
              <Link href="/" className={GHOST}>
                Homepage
              </Link>
            </div>
          </PageHero>
        </main>
      </body>
    </html>
  );
}
