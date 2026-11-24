import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalCountdown, LocalTime, LocalTimeZone } from "./LocalTime";

describe("LocalTime", () => {
  it("serves UTC from the server render, with the fallback for a missing value", () => {
    expect(renderToString(<LocalTime value="2026-09-11T13:35:00Z" style="clock" />)).toBe("01:35 PM");
    expect(renderToString(<LocalTime value={null} style="clock" fallback="TBC" />)).toBe("TBC");
    expect(renderToString(<LocalTime value={undefined} style="clock" />)).toBe("—");
  });

  it("switches to the viewer's own zone once hydrated", () => {
    const host = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
    const { container } = render(<LocalTime value="2026-09-11T13:35:00Z" style="clock" />);

    expect(container).toHaveTextContent(host.format(new Date("2026-09-11T13:35:00Z")));
  });
});

describe("LocalTimeZone", () => {
  it("says UTC on the server and the host zone after hydration", () => {
    expect(renderToString(<LocalTimeZone />)).toBe("UTC");

    const { container } = render(<LocalTimeZone />);
    expect(container).toHaveTextContent(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });
});

describe("LocalCountdown", () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: new Date("2026-09-11T00:00:00Z") });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing on the server, before a session, or once it has started", () => {
    expect(renderToString(<LocalCountdown value="2026-09-13T00:00:00Z" />)).toBe("");
    expect(render(<LocalCountdown value={undefined} />).container).toBeEmptyDOMElement();
    expect(render(<LocalCountdown value="2026-09-10T00:00:00Z" />).container).toBeEmptyDOMElement();
  });

  it("counts down and re-reads the clock every minute", () => {
    render(<LocalCountdown value="2026-09-13T01:30:00Z" />);
    expect(screen.getByText("02D 01H 30M")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(screen.getByText("02D 01H 29M")).toBeInTheDocument();
  });
});
