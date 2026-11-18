import { useSyncExternalStore } from "react";

/** The visitor's answer to the analytics banner; "ask" until they give one. */
export type AnalyticsConsent = "granted" | "denied" | "ask";

const STORAGE_KEY = "f1ai:analytics-consent";

/** gtag's own cookies: `_ga` and one `_ga_<container>` per property. */
const GA_COOKIE = /^_ga(_|$)/;

const listeners = new Set<() => void>();
/** This page's answer, so a choice holds even where storage is blocked. */
let answered: AnalyticsConsent | null = null;
/** The footer's "Cookie settings" brought the banner back. */
let reopened = false;

function readStored(): AnalyticsConsent {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "granted" || stored === "denied" ? stored : "ask";
  } catch {
    // Storage blocked (private mode, site data off): ask, never assume yes.
    return "ask";
  }
}

function notify(): void {
  for (const listener of listeners) listener();
}

/** Another tab answered: drop this page's copy and read theirs. */
function onStorage(): void {
  answered = null;
  notify();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  if (listeners.size === 1) window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}

function getConsent(): AnalyticsConsent {
  return answered ?? readStored();
}

function getPrompt(): boolean {
  return reopened || getConsent() === "ask";
}

/** Records the visitor's answer and closes the banner. */
export function chooseAnalytics(choice: "granted" | "denied"): void {
  answered = choice;
  reopened = false;
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Storage blocked: `answered` keeps the choice for this page, and the banner asks again next visit.
  }
  notify();
}

/** Shows the banner again so the visitor can change their answer. */
export function reopenConsent(): void {
  reopened = true;
  notify();
}

/**
 * Expires gtag's cookies. gtag writes them on the widest domain the browser
 * accepts, so each is cleared on the host and on every parent domain.
 */
export function clearAnalyticsCookies(): void {
  const names = document.cookie
    .split(";")
    .map((pair) => pair.split("=")[0].trim())
    .filter((name) => GA_COOKIE.test(name));
  const labels = location.hostname.split(".");
  const domains = labels.map((_, i) => labels.slice(i).join("."));
  for (const name of names) {
    document.cookie = `${name}=; max-age=0; path=/`;
    for (const domain of domains) document.cookie = `${name}=; max-age=0; path=/; domain=${domain}`;
  }
}

/** The visitor's answer; null while server rendering and hydrating, when it can't be known. */
export function useAnalyticsConsent(): AnalyticsConsent | null {
  return useSyncExternalStore(subscribe, getConsent, () => null);
}

/** Whether the banner should show; never during server rendering, so a returning visitor sees no flash. */
export function useConsentPrompt(): boolean {
  return useSyncExternalStore(subscribe, getPrompt, () => false);
}
