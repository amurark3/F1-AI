"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
}

/**
 * The last-resort boundary: an error no route-level boundary caught replaces the
 * whole root layout with this page. React swallows errors a boundary catches,
 * so without this report Sentry would never hear about them.
 */
export default function GlobalError({ error }: Readonly<GlobalErrorProps>) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        {/* The App Router exposes no status code for an error, so 0 renders
            Next.js's generic error message. */}
        <NextError statusCode={0} />
      </body>
    </html>
  );
}
