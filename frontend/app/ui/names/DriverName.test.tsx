import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { CHAMPION_STATS, DIRECTORY_2026, TEAMS_2026 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";

import { DriverName } from "./DriverName";

// The directory is read for the calendar year, so match any season.
const DIRECTORY_URL = apiUrl("/api/profiles/:year/directory");

/** Serves the captured directory and counts the requests for it. */
function serveDirectory(): { requests: () => number } {
  let count = 0;
  server.use(
    http.get(DIRECTORY_URL, () => {
      count += 1;
      return HttpResponse.json(DIRECTORY_2026);
    }),
  );
  return { requests: () => count };
}

/** A row of the 2026 championship table: code + f1db name, no surname. */
function standingsRow(code: string): { name: string; code: string } {
  const row = TEAMS_2026.drivers?.find((driver) => driver.code === code);
  if (!row?.code) throw new Error(`no ${code} in the captured table`);
  return { name: row.driver, code: row.code };
}

describe("DriverName", () => {
  it("prints the full name as sent, by default, without reading the directory", () => {
    const directory = serveDirectory();
    renderWithProviders(<DriverName {...standingsRow("SAI")} className="font-bold" />);

    const name = screen.getByText("Carlos Sainz Jr.");
    expect(name).toHaveClass("font-bold");
    expect(name).not.toHaveAttribute("title");
    expect(directory.requests()).toBe(0);
  });

  it("prints a champion's surname from the payload, with the full name on hover", () => {
    const directory = serveDirectory();
    const fangio = CHAMPION_STATS.most_driver_titles?.[2];
    if (!fangio) throw new Error("no third champion in the capture");
    renderWithProviders(<DriverName variant="last" name={fangio.name} lastName={fangio.last_name} />);

    expect(screen.getByText("Fangio")).toHaveAttribute("title", "Juan Manuel Fangio");
    expect(screen.queryByText(/Juan Fangio/)).not.toBeInTheDocument();
    expect(directory.requests()).toBe(0);
  });

  it("reads this season's surname from the directory when the payload sends only the code", async () => {
    serveDirectory();
    renderWithProviders(
      <>
        <DriverName variant="last" {...standingsRow("SAI")} />
        <DriverName variant="last" {...standingsRow("HUL")} />
        <DriverName variant="last" {...standingsRow("HIR")} />
      </>,
    );

    // Until the directory lands, the full name stands in: never a split.
    expect(screen.getByText("Carlos Sainz Jr.")).toBeInTheDocument();
    expect(await screen.findByText("Sainz Jr.")).toHaveAttribute("title", "Carlos Sainz Jr.");
    expect(screen.getByText("Hülkenberg")).toBeInTheDocument();
    expect(screen.getByText("Hirakawa")).toHaveAttribute("title", "Ryō Hirakawa");
  });

  it("prints the code the payload sends, or this season's code for the name", async () => {
    const directory = serveDirectory();
    const { rerender } = renderWithProviders(<DriverName variant="code" {...standingsRow("ANT")} />);

    expect(screen.getByText("ANT")).toHaveAttribute("title", "Kimi Antonelli");
    expect(directory.requests()).toBe(0);

    rerender(<DriverName variant="code" name="Kimi Antonelli" />);
    expect(await screen.findByText("ANT")).toBeInTheDocument();
    expect(directory.requests()).toBe(1);
  });

  it("prints surname then code in a table row, the code in the mono caption tone", async () => {
    serveDirectory();
    renderWithProviders(<DriverName variant="codeLast" {...standingsRow("SAI")} />);

    const code = await screen.findByText("SAI");
    expect(code).toHaveClass("font-mono", "text-rc-ink-3");
    expect(code.parentElement).toHaveTextContent("Sainz Jr.SAI");
    expect(code.parentElement).toHaveAttribute("title", "Carlos Sainz Jr.");
  });

  it("reads nothing more when the payload sends both the surname and the code", () => {
    const directory = serveDirectory();
    renderWithProviders(<DriverName variant="codeLast" name="Ryō Hirakawa" lastName="Hirakawa" code="HIR" />);

    expect(screen.getByText("Hirakawa").parentElement).toHaveTextContent("HirakawaHIR");
    expect(directory.requests()).toBe(0);
  });

  it("reads no directory for another season's row, and prints its full name", () => {
    const directory = serveDirectory();
    renderWithProviders(<DriverName variant="last" name="Nyck de Vries" code="DEV" year={2023} />);

    expect(screen.getByText("Nyck de Vries")).not.toHaveAttribute("title");
    expect(directory.requests()).toBe(0);
  });

  it("falls back to the full name, with no code, when the directory cannot be read", async () => {
    let failed = false;
    server.use(
      http.get(DIRECTORY_URL, () => {
        failed = true;
        return HttpResponse.json({ error: "down" }, { status: 503 });
      }),
    );
    renderWithProviders(<DriverName variant="codeLast" name="Nyck de Vries" />);

    await waitFor(() => expect(failed).toBe(true));
    const name = screen.getByText("Nyck de Vries");
    expect(name.parentElement).toHaveTextContent(/^Nyck de Vries$/);
    expect(name.parentElement).not.toHaveAttribute("title");
  });
});
