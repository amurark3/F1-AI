import { describe, expect, it, vi } from "vitest";

import CalendarRedirectPage from "./calendar/page";
import ConsumerRedirectPage from "./consumer/page";
import PredictionsRedirectPage from "./predictions/page";
import IntelPage from "./race-control/intel/page";
import RaceControlPredictionsRedirectPage from "./race-control/predictions/page";

const { redirect } = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect }));

describe("renamed routes", () => {
  it.each([
    ["/calendar", CalendarRedirectPage, "/race-control"],
    ["/consumer", ConsumerRedirectPage, "/race-control/engineer"],
    ["/predictions", PredictionsRedirectPage, "/race-control/grand-prix"],
    ["/race-control/intel", IntelPage, "/race-control/constructors"],
    ["/race-control/predictions", RaceControlPredictionsRedirectPage, "/race-control/grand-prix"],
  ])("send %s to %s", (_from, page, target) => {
    redirect.mockClear();

    page();

    expect(redirect).toHaveBeenCalledWith(target);
  });
});
