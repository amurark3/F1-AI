import { afterEach, describe, expect, it, vi } from "vitest";

async function loadBase(configured: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_URL", configured);
  return (await import("./api")).API_BASE;
}

describe("API_BASE", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses the configured origin", async () => {
    await expect(loadBase(" https://api.example.com ")).resolves.toBe("https://api.example.com");
  });

  it("falls back to localhost when the variable is blank", async () => {
    await expect(loadBase("  ")).resolves.toBe("http://localhost:8000");
  });
});
