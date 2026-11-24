import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServerStatusNotice from "./ServerStatusNotice";

import type * as StoreModule from "../lib/serverStatus";

type ServerState = StoreModule.ServerState;

const hook = vi.hoisted(() => ({ useServerStatus: vi.fn() }));
vi.mock("../hooks/useServerStatus", () => hook);
const store = vi.hoisted(() => ({ retryServerProbe: vi.fn(), dismissServerNotice: vi.fn() }));
vi.mock("../lib/serverStatus", async (importOriginal) => ({
  ...(await importOriginal<typeof StoreModule>()),
  ...store,
}));

const server = (patch: Partial<ServerState>): ServerState => ({
  status: "ready",
  detail: null,
  stage: null,
  lit: 0,
  run: 1,
  waited: false,
  warmingSince: null,
  dismissedRun: 0,
  launchedRun: 0,
  ...patch,
});

const region = () => screen.getByRole("status", { name: "Server status" });

describe("ServerStatusNotice", () => {
  beforeEach(() => vi.clearAllMocks());

  it("stays mounted and empty while the backend is up", () => {
    hook.useServerStatus.mockReturnValue(server({}));
    render(<ServerStatusNotice />);

    expect(region()).toBeEmptyDOMElement();
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("announces the stage while starting, then back online", () => {
    hook.useServerStatus.mockReturnValue(server({ status: "warming", detail: "Loading the race prediction model" }));
    const { rerender } = render(<ServerStatusNotice />);
    expect(region()).toHaveTextContent("Server starting: Loading the race prediction model");

    hook.useServerStatus.mockReturnValue(server({ status: "warming" }));
    rerender(<ServerStatusNotice />);
    expect(region()).toHaveTextContent("Server starting: Server starting up");

    hook.useServerStatus.mockReturnValue(server({ status: "ready", waited: true }));
    rerender(<ServerStatusNotice />);
    expect(region()).toHaveTextContent("Back online");
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("offers Try again and Dismiss in a card that is not a dialog once the server stops answering", async () => {
    hook.useServerStatus.mockReturnValue(server({ status: "unreachable" }));
    render(<ServerStatusNotice />);
    const user = userEvent.setup();

    expect(region()).toHaveTextContent("Server isn't responding");
    const card = screen.getByRole("group", { name: "Server isn't responding" });
    expect(card).toHaveTextContent("No answer for 2 minutes. It may be redeploying or down.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(document.body);

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(store.retryServerProbe).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(store.dismissServerNotice).toHaveBeenCalledTimes(1);
  });

  it("shows nothing for an unreachable run the visitor dismissed", () => {
    hook.useServerStatus.mockReturnValue(server({ status: "unreachable", dismissedRun: 1 }));
    render(<ServerStatusNotice />);

    expect(region()).toBeEmptyDOMElement();
    expect(screen.queryByRole("group")).toBeNull();
  });
});
