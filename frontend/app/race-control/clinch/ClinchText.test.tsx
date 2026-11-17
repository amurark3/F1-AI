import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClinchResponse } from "@/app/lib/clinch";
import type { SectionStatus } from "@/app/ui/section/sectionState";
import { CLINCH_2026 } from "@/test/fixtures";

import { ClinchAside, ClinchHeroLine, EntrantClinch } from "./ClinchText";
import { useClinch } from "./useClinch";

vi.mock("./useClinch", () => ({ useClinch: vi.fn() }));

const { afterRound19, afterRound20 } = CLINCH_2026;
/** A season the calculator does not cover (before 2025): both championships are null. */
const UNCOVERED: ClinchResponse = { ...afterRound20, year: 2024, drivers: null, constructors: null };
const PLAIN = "119 points clear of Max Verstappen after round 20.";
const MERCEDES = { name: "Mercedes" };

function given(status: SectionStatus, data?: ClinchResponse): void {
  const failed = status === "stale" || status === "failed";
  vi.mocked(useClinch).mockReturnValue({
    status,
    data,
    reason: failed ? "Request failed: 500" : null,
    refreshing: false,
    retry: vi.fn(),
  });
}

beforeEach(() => {
  vi.mocked(useClinch).mockReset();
});

describe("ClinchHeroLine", () => {
  it("says where a decided title was clinched, with the place in bold", () => {
    given("ready", afterRound20);
    render(<ClinchHeroLine year={2026} table="drivers" fallback={PLAIN} />);

    const strong = screen.getByText("Clinched in Mexico City");
    expect(strong.tagName).toBe("B");
    expect(strong.parentElement).toHaveTextContent(
      "Clinched in Mexico City with four races to spare: 119 points clear, and only 100 left to win.",
    );
    expect(screen.queryByText(PLAIN)).not.toBeInTheDocument();
    expect(vi.mocked(useClinch)).toHaveBeenCalledWith(2026);
  });

  it("marks a clinch on provisional results as provisional", () => {
    given("ready", afterRound19);
    render(<ClinchHeroLine year={2026} table="drivers" fallback={PLAIN} />);

    expect(screen.getByText("Provisionally clinched in Mexico City").tagName).toBe("B");
  });

  it("says what the leader must do at the next event while the title is open", () => {
    given("ready", afterRound19);
    const { container } = render(<ClinchHeroLine year={2026} table="constructors" fallback={PLAIN} />);

    expect(screen.getByText("Mercedes clinch in São Paulo if they outscore Ferrari by 3.")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
  });

  it("holds the line's place with a skeleton while the answer is out", () => {
    given("pending");
    const { container } = render(<ClinchHeroLine year={2026} table="drivers" fallback={PLAIN} />);

    expect(container.querySelector(".motion-safe\\:animate-pulse")).not.toBeNull();
    expect(screen.queryByText(PLAIN)).not.toBeInTheDocument();
  });

  it.each([
    ["the endpoint fails", "failed" as const, undefined],
    ["the season is not covered", "ready" as const, UNCOVERED],
  ])("prints the plain lead line when %s", (_case, status, data) => {
    given(status, data);
    render(<ClinchHeroLine year={2026} table="drivers" fallback={PLAIN} />);

    expect(screen.getByText(PLAIN)).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
  });

  it("keeps the sentence and says it could not refresh", () => {
    given("stale", afterRound20);
    render(<ClinchHeroLine year={2026} table="drivers" fallback={PLAIN} />);

    expect(screen.getByText("Clinched in Mexico City")).toBeInTheDocument();
    expect(screen.getByText("Couldn't refresh")).toBeInTheDocument();
  });
});

describe("ClinchAside", () => {
  it("names where the leader can clinch, as an eyebrow caption", () => {
    given("ready", afterRound19);
    render(<ClinchAside year={2026} table="constructors" />);

    expect(screen.getByText("Mercedes can clinch in São Paulo")).toHaveClass("font-mono", "uppercase");
  });

  it("names where the title was clinched once it is decided", () => {
    given("ready", afterRound20);
    render(<ClinchAside year={2026} table="constructors" />);

    expect(screen.getByText("Mercedes clinched in São Paulo")).toBeInTheDocument();
  });

  it("shows a skeleton while pending", () => {
    given("pending");
    const { container } = render(<ClinchAside year={2026} table="constructors" />);

    expect(container.querySelector(".motion-safe\\:animate-pulse")).not.toBeNull();
  });

  it.each([
    ["the endpoint fails", "failed" as const, undefined],
    ["the season is not covered", "ready" as const, UNCOVERED],
  ])("renders nothing when %s", (_case, status, data) => {
    given(status, data);
    const { container } = render(<ClinchAside year={2026} table="constructors" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the caption and says it could not refresh", () => {
    given("stale", afterRound19);
    render(<ClinchAside year={2026} table="constructors" />);

    expect(screen.getByText("Mercedes can clinch in São Paulo")).toBeInTheDocument();
    expect(screen.getByText("Couldn't refresh")).toBeInTheDocument();
  });
});

describe("EntrantClinch", () => {
  it("gives the champion team its own clause", () => {
    given("ready", afterRound20);
    render(<EntrantClinch year={2026} table="constructors" entrant={MERCEDES} />);

    expect(screen.getByText("Clinched in São Paulo with three races to spare.")).toBeInTheDocument();
  });

  it("gives the champion driver theirs, matched by code", () => {
    given("ready", afterRound20);
    render(<EntrantClinch year={2026} table="drivers" entrant={{ name: "Kimi Antonelli", code: "ANT" }} />);

    expect(screen.getByText("Clinched in Mexico City with four races to spare.")).toBeInTheDocument();
  });

  it("tells a rival still alive what keeps them in it", () => {
    given("ready", afterRound19);
    render(<EntrantClinch year={2026} table="constructors" entrant={{ name: "Ferrari" }} />);

    expect(screen.getByText("Ferrari stay in it unless Mercedes outscore them by 3 or more.")).toBeInTheDocument();
  });

  it.each([
    ["the team is out of the fight", "ready" as const, afterRound19],
    ["the answer is still out", "pending" as const, undefined],
    ["the endpoint fails", "failed" as const, undefined],
    ["the season is not covered", "ready" as const, UNCOVERED],
  ])("renders nothing when %s", (_case, status, data) => {
    given(status, data);
    const { container } = render(<EntrantClinch year={2026} table="constructors" entrant={{ name: "Red Bull" }} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the clause and says it could not refresh", () => {
    given("stale", afterRound20);
    render(<EntrantClinch year={2026} table="constructors" entrant={MERCEDES} />);

    expect(screen.getByText("Clinched in São Paulo with three races to spare.")).toBeInTheDocument();
    expect(screen.getByText("Couldn't refresh")).toBeInTheDocument();
  });
});
