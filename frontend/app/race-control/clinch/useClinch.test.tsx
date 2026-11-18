import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { useServerStatus, type ServerState } from "@/app/hooks/useServerStatus";
import { CLINCH_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { TestProviders } from "@/test/render";

import { useClinch } from "./useClinch";

vi.mock("@/app/hooks/useServerStatus", () => ({ useServerStatus: vi.fn() }));

describe("useClinch", () => {
  it("reads the season's clinch answer from its own endpoint", async () => {
    vi.mocked(useServerStatus).mockReturnValue({ status: "ready" } as ServerState);
    server.use(
      http.get(apiUrl("/api/race-control/standings/2026/clinch"), () =>
        HttpResponse.json(CLINCH_2026.afterRound20 as never),
      ),
    );

    const { result } = renderHook(() => useClinch(2026), { wrapper: TestProviders });

    expect(result.current.status).toBe("pending");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data?.constructors?.decided_at?.venue).toBe("São Paulo");
  });
});
