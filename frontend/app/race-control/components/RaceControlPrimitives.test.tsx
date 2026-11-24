import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { f1, rc } from "@/app/ui/tokens";

import {
  InfoRow,
  InlineNotice,
  PageStack,
  Panel,
  SectionLoader,
  SkeletonPanel,
  StatusPill,
  WorkspaceSplit,
  WrapRow,
} from "./RaceControlPrimitives";

/** DRS green in any spelling a class or style might carry. */
const DRS_GREEN = /00ff78|0,\s*255,\s*120/i;

describe("Panel", () => {
  it("is a div on the panel surface with a hairline border", () => {
    const { container } = render(<Panel className="p-5">Body</Panel>);

    const panel = container.firstElementChild;
    expect(panel?.tagName).toBe("DIV");
    expect(panel).toHaveClass("border-rc-line", "bg-(--surface)", "overflow-hidden", "p-5");
    expect(container.querySelector("[data-panel-accent]")).toBeNull();
  });

  it("renders as a section and draws an accent rule in the colour given", () => {
    const { container } = render(
      <Panel as="section" accent={f1.red}>
        Body
      </Panel>,
    );

    expect(container.firstElementChild?.tagName).toBe("SECTION");
    expect(container.querySelector("[data-panel-accent]")).toHaveStyle({ backgroundColor: f1.red });
  });
});

describe("layout rows", () => {
  it("stacks, splits and wraps their children", () => {
    render(
      <PageStack className="stack">
        <WorkspaceSplit className="split">
          <WrapRow className="wrap">
            <span>Child</span>
          </WrapRow>
        </WorkspaceSplit>
      </PageStack>,
    );

    const wrap = screen.getByText("Child").parentElement;
    expect(wrap).toHaveClass("wrap", "flex-wrap");
    expect(wrap?.parentElement).toHaveClass("split", "flex-col");
    expect(wrap?.parentElement?.parentElement).toHaveClass("stack", "gap-5");
  });

  it("keeps their default spacing with no class given", () => {
    const { container } = render(
      <>
        <PageStack>a</PageStack>
        <WorkspaceSplit>b</WorkspaceSplit>
        <WrapRow>c</WrapRow>
      </>,
    );

    const [stack, split, wrap] = Array.from(container.children);
    expect(stack).toHaveClass("gap-5");
    expect(split).toHaveClass("gap-5");
    expect(wrap).toHaveClass("gap-3");
  });
});

describe("StatusPill", () => {
  it("is neutral by default, never DRS green", () => {
    render(<StatusPill>Classification</StatusPill>);

    const pill = screen.getByText("Classification");
    expect(pill).toHaveStyle({ color: rc.ink2, borderColor: `${rc.ink2}55`, backgroundColor: `${rc.ink2}14` });
    expect(pill.getAttribute("style")).not.toMatch(DRS_GREEN);
  });

  it("takes the colour that carries its status", () => {
    render(<StatusPill color={rc.gold}>In Progress</StatusPill>);

    expect(screen.getByText("In Progress")).toHaveStyle({ color: rc.gold });
  });
});

describe("SkeletonPanel", () => {
  it("is a neutral block that pulses only when motion is welcome", () => {
    const { container, rerender } = render(<SkeletonPanel />);

    const block = container.firstElementChild;
    expect(block).toHaveClass("h-32", "bg-(--surface-raised)", "border-rc-line", "motion-safe:animate-pulse");
    expect(block).not.toHaveClass("animate-pulse");

    rerender(<SkeletonPanel className="h-80" />);
    expect(container.firstElementChild).toHaveClass("h-80");
    expect(container.firstElementChild).not.toHaveClass("h-32");
  });
});

describe("loaders", () => {
  it("SectionLoader announces a smaller red spinner over two skeletons", () => {
    const { container } = render(<SectionLoader />);

    expect(screen.getByRole("status")).toHaveTextContent("Refreshing section");
    expect(screen.getByText("Updating this panel from the latest available data.")).toBeInTheDocument();
    expect(container.querySelector("[data-spinner]")).toHaveClass("border-t-f1-red", "h-4", "w-4");
    expect(container.querySelectorAll(".h-72")).toHaveLength(2);
    expect(container.innerHTML).not.toMatch(DRS_GREEN);
  });

  it("SectionLoader takes its own title, detail and class", () => {
    render(<SectionLoader title="Building race debrief" detail="Refreshing the podium." className="mt-3" />);

    const status = screen.getByRole("status");
    expect(status).toHaveClass("mt-3");
    expect(status).toHaveTextContent("Building race debrief");
    expect(status).toHaveTextContent("Refreshing the podium.");
  });
});

describe("InlineNotice", () => {
  it.each([
    ["info", "border-[#3671C6]/35"],
    ["warning", "border-[#FFF200]/30"],
    ["error", "border-[#E10600]/35"],
  ] as const)("styles the %s tone", (tone, border) => {
    const { container } = render(
      <InlineNotice title="Notice" tone={tone}>
        Body text
      </InlineNotice>,
    );

    expect(container.firstElementChild).toHaveClass(border);
    expect(screen.getByText("Notice")).toBeInTheDocument();
    expect(screen.getByText("Body text")).toBeInTheDocument();
  });

  it("is informational by default", () => {
    const { container } = render(<InlineNotice title="Heads up">Body</InlineNotice>);

    expect(container.firstElementChild).toHaveClass("border-[#3671C6]/35");
  });
});

describe("InfoRow", () => {
  it("pairs a term with its value inside a description list", () => {
    render(
      <dl>
        <InfoRow label="Race order" value="22 drivers" />
      </dl>,
    );

    expect(screen.getByRole("term")).toHaveTextContent("Race order");
    expect(screen.getByRole("definition")).toHaveTextContent("22 drivers");
  });
});
