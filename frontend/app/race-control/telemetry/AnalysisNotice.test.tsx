import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";

import type { AnalysisStatus } from "./telemetryModel";
import type { AnalysisData } from "./useAnalysisData";

function gate(state: Partial<AnalysisData<AnalysisStatus>>) {
  return render(
    <AnalysisGate
      state={{ data: undefined, error: undefined, loading: false, ...state }}
      loadingTitle="Loading the lap"
    />,
  );
}

const READY: AnalysisStatus = { available: true, pending: false };

describe("AnalysisGate", () => {
  it("shows a loader while the first answer is on its way", () => {
    gate({ loading: true });
    expect(screen.getByText("Loading the lap")).toBeInTheDocument();
    expect(screen.getByText("Reading lap and car data from OpenF1.")).toBeInTheDocument();
  });

  it("says the service did not answer when the fetch failed", () => {
    gate({ error: new Error("down") });
    expect(screen.getByText("Could not load")).toBeInTheDocument();
  });

  it("renders nothing when there is no answer yet or the answer is available", () => {
    expect(gate({}).container).toBeEmptyDOMElement();
    expect(gate({ data: READY }).container).toBeEmptyDOMElement();
  });

  it("keeps the loader up with the backend's own words while a load is pending", () => {
    gate({ data: { available: false, pending: true, message: "Fetching lap 14." } });
    expect(screen.getByText("Loading the lap")).toBeInTheDocument();
    expect(screen.getByText("Fetching lap 14.")).toBeInTheDocument();
  });

  it("falls back to a stock line when a pending answer has no message", () => {
    gate({ data: { available: false, pending: true } });
    expect(screen.getByText("Still loading from OpenF1.")).toBeInTheDocument();
  });

  it("explains the live-session closure and an unavailable reason with the error ref", () => {
    gate({ data: { available: false, pending: false, reason: "openf1_live", message: "Closed." } });
    expect(screen.getByText("OpenF1 is closed during live sessions")).toBeInTheDocument();
    expect(screen.queryByText(/ref /)).not.toBeInTheDocument();
  });

  it("titles other reasons plainly and shows the error reference when there is one", () => {
    gate({ data: { available: false, pending: false, reason: "error", message: "Boom.", error_id: "abc123" } });
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
    expect(screen.getByText("(ref abc123)")).toBeInTheDocument();
  });

  it("also treats an unavailable OpenF1 as a plain nothing to show", () => {
    gate({ data: { available: false, pending: false, reason: "openf1_unavailable", message: "Gone." } });
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
  });

  it("shows the message of a missing session", () => {
    gate({ data: { available: false, pending: false, reason: "no_session", message: "No session." } });
    expect(screen.getByText("No session.")).toBeInTheDocument();
  });
});

describe("ModeledNote", () => {
  it("renders nothing without modelled figures", () => {
    expect(render(<ModeledNote />).container).toBeEmptyDOMElement();
    expect(render(<ModeledNote modeled={[]} />).container).toBeEmptyDOMElement();
  });

  it("names the modelled figures, with an unknown key shown as is, and any extra line", () => {
    render(<ModeledNote modeled={["distance", "mystery"]} extra="Fuel burn is assumed." />);
    expect(screen.getByText("Modelled")).toBeInTheDocument();
    expect(screen.getByText(/distance along the lap \(integrated from speed\), mystery are derived/)).toHaveTextContent(
      "Fuel burn is assumed.",
    );
  });

  it("omits the extra line when there is none", () => {
    render(<ModeledNote modeled={["corners"]} />);
    expect(screen.getByText(/corner positions \(MultiViewer\) are derived/)).toBeInTheDocument();
  });
});

describe("AnalysisWarnings", () => {
  it("lists each warning, and shows nothing without any", () => {
    expect(render(<AnalysisWarnings />).container).toBeEmptyDOMElement();
    expect(render(<AnalysisWarnings warnings={[]} />).container).toBeEmptyDOMElement();
    render(<AnalysisWarnings warnings={["One sample was missing."]} />);
    expect(screen.getByText("One sample was missing.")).toBeInTheDocument();
  });
});
