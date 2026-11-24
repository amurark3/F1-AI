import { afterEach, describe, expect, it, vi } from "vitest";

async function loadOptions(env: Record<string, string | undefined>) {
  vi.resetModules();
  for (const [key, value] of Object.entries({
    NEXT_PUBLIC_SENTRY_DSN: "",
    NEXT_PUBLIC_VERCEL_ENV: undefined,
    ...env,
  })) {
    vi.stubEnv(key, value);
  }
  return (await import("./errorTracking")).SENTRY_OPTIONS;
}

describe("SENTRY_OPTIONS", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is off without a DSN", async () => {
    const options = await loadOptions({});

    expect(options.enabled).toBe(false);
  });

  it("turns on with a DSN and never collects user data", async () => {
    const options = await loadOptions({ NEXT_PUBLIC_SENTRY_DSN: " https://key@sentry.example/1 " });

    expect(options).toMatchObject({
      dsn: "https://key@sentry.example/1",
      enabled: true,
      dataCollection: { userInfo: false, cookies: false, httpBodies: [] },
    });
  });

  it("falls back to Node's environment off Vercel", async () => {
    const options = await loadOptions({});

    expect(options.environment).toBe("test");
  });

  it("names the Vercel environment when there is one", async () => {
    const options = await loadOptions({ NEXT_PUBLIC_VERCEL_ENV: "preview" });

    expect(options.environment).toBe("preview");
  });
});
