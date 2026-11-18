"use client";

import Script from "next/script";
import { useEffect } from "react";

import { clearAnalyticsCookies, useAnalyticsConsent } from "./analyticsConsent";

/**
 * Loads Google Analytics only after the visitor allows it. GA4's enhanced
 * measurement counts client-side route changes itself, so one config call covers
 * every page. Declining stops a tag already loaded on this page and clears its cookies.
 */
export function GoogleAnalytics({ id }: { id: string }) {
  const consent = useAnalyticsConsent();

  useEffect(() => {
    if (consent === null) return;
    // gtag's documented opt-out switch, read before every hit it sends.
    Reflect.set(window, `ga-disable-${id}`, consent !== "granted");
    if (consent !== "granted") clearAnalyticsCookies();
  }, [consent, id]);

  if (consent !== "granted") return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${id}`} strategy="afterInteractive" />
      <Script id="google-analytics" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${id}');`}
      </Script>
    </>
  );
}
