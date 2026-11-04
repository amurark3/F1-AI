import { describe, expect, it } from "vitest";

import {
  CHAMPION_STATS,
  DIRECTORY_2023,
  DIRECTORY_2026,
  OPENF1_DRIVERS_MEXICO_2026,
  TEAMS_2026,
} from "@/test/fixtures";

import {
  driverCode,
  driverLabel,
  driverSurname,
  findDirectoryDriver,
  findDirectoryTeam,
  foldName,
  teamLabel,
  type DriverIdentity,
} from "./names";

/** A driver row of the 2026 championship table, as the teams endpoint sends it (code + f1db name). */
function standingsRow(code: string): DriverIdentity {
  const row = TEAMS_2026.drivers?.find((driver) => driver.code === code);
  if (!row) throw new Error(`no ${code} in the captured table`);
  return { name: row.driver, code: row.code };
}

/** A 2023 driver as that season's directory lists them. */
function season2023(code: string): DriverIdentity {
  const row = DIRECTORY_2023.drivers.find((driver) => driver.code === code);
  if (!row) throw new Error(`no ${code} in the 2023 directory`);
  return { name: row.name, code: row.code, year: 2023 };
}

/** A team as OpenF1 spells it on the Mexico City entry list. */
function openF1Team(code: string): string {
  const team = OPENF1_DRIVERS_MEXICO_2026.find((driver) => driver.name_acronym === code)?.team_name;
  if (!team) throw new Error(`no team for ${code} in the OpenF1 list`);
  return team;
}

describe("foldName", () => {
  it("ignores case, accents and punctuation, as the backend's fold does", () => {
    expect(foldName("Nico Hülkenberg")).toBe("nico hulkenberg");
    expect(foldName("Sergio Pérez")).toBe(foldName("Sergio PEREZ"));
    expect(foldName("  Carlos Sainz Jr. ")).toBe("carlos sainz jr");
    expect(foldName("Ryō Hirakawa")).toBe("ryo hirakawa");
  });
});

describe("findDirectoryDriver", () => {
  it("finds this season's driver by f1db id, then code, then folded name", () => {
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "", id: "nico-hulkenberg" })?.last_name).toBe("Hülkenberg");
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "", code: "sai" })?.id).toBe("carlos-sainz-jr");
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "Sergio Perez" })?.code).toBe("PER");
  });

  it("passes over an id from no row and still tries the code", () => {
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "", id: "nyck-de-vries", code: "HIR" })?.name).toBe(
      "Ryō Hirakawa",
    );
  });

  it("finds nobody for a driver who is not on this season's list", () => {
    expect(findDirectoryDriver(DIRECTORY_2026, season2023("DEV"))).toBeNull();
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "Nyck de Vries" })).toBeNull();
    // Nikola Tsolov drove Mexico City FP1 only, so the directory has no "TSO".
    expect(findDirectoryDriver(DIRECTORY_2026, { code: "TSO" })).toBeNull();
    expect(findDirectoryDriver(undefined, standingsRow("SAI"))).toBeNull();
  });

  it("never reads a row of another season against this season's list, so a reused code finds nobody", () => {
    // f1db: in 2014 "VER" is Jean-Éric Vergne; in 2026 it is Max Verstappen.
    expect(findDirectoryDriver(DIRECTORY_2026, { name: "Jean-Éric Vergne", code: "VER", year: 2014 })).toBeNull();
    expect(findDirectoryDriver(DIRECTORY_2023, season2023("DEV"))?.last_name).toBe("De Vries");
  });
});

describe("driverSurname", () => {
  it("takes the surname a payload carries, as f1db stores it", () => {
    const fangio = CHAMPION_STATS.most_driver_titles?.find((entry) => entry.name === "Juan Manuel Fangio");
    expect(driverSurname({ name: "Juan Manuel Fangio", lastName: fangio?.last_name })).toBe("Fangio");
  });

  it("reads this season's surname from the directory by code: suffixes, accents and macrons intact", () => {
    expect(driverSurname(standingsRow("SAI"), DIRECTORY_2026)).toBe("Sainz Jr.");
    expect(driverSurname(standingsRow("HUL"), DIRECTORY_2026)).toBe("Hülkenberg");
    expect(driverSurname(standingsRow("HIR"), DIRECTORY_2026)).toBe("Hirakawa");
    expect(driverSurname(standingsRow("ANT"), DIRECTORY_2026)).toBe("Antonelli");
  });

  it("keeps the particle f1db capitalises when the surname stands alone: De Vries, never Vries", () => {
    expect(driverSurname(season2023("DEV"), DIRECTORY_2023)).toBe("De Vries");
  });

  it("has no surname to give when neither the payload nor the directory knows one", () => {
    expect(driverSurname(standingsRow("SAI"))).toBeNull();
    expect(driverSurname(season2023("DEV"), DIRECTORY_2026)).toBeNull();
    expect(driverSurname({ name: "Nyck de Vries", lastName: "  " })).toBeNull();
  });
});

describe("driverCode", () => {
  it("takes the payload's code, else this season's code for the same f1db name", () => {
    expect(driverCode(standingsRow("HIR"))).toBe("HIR");
    expect(driverCode({ name: "Kimi Antonelli" }, DIRECTORY_2026)).toBe("ANT");
  });

  it("has no code to give rather than making one up from the name", () => {
    expect(driverCode({ name: "Kimi Antonelli" })).toBeNull();
    expect(driverCode({ name: "Juan Manuel Fangio", code: "" }, DIRECTORY_2026)).toBeNull();
  });
});

describe("driverLabel", () => {
  it("prints the full name exactly as the payload sends it", () => {
    expect(driverLabel(standingsRow("SAI"), "full", DIRECTORY_2026)).toBe("Carlos Sainz Jr.");
    expect(driverLabel(season2023("DEV"), "full", DIRECTORY_2023)).toBe("Nyck de Vries");
  });

  it("prints the surname, the code, or both, the surname first as the mockups' tables do", () => {
    const sainz = standingsRow("SAI");
    expect(driverLabel(sainz, "last", DIRECTORY_2026)).toBe("Sainz Jr.");
    expect(driverLabel(sainz, "code", DIRECTORY_2026)).toBe("SAI");
    expect(driverLabel(sainz, "codeLast", DIRECTORY_2026)).toBe("Sainz Jr. SAI");
    expect(driverLabel(season2023("DEV"), "codeLast", DIRECTORY_2023)).toBe("De Vries DEV");
  });

  it("falls back to the full name, never a guess, for every part it cannot read from data", () => {
    const deVries = season2023("DEV");
    expect(driverLabel(deVries, "last", DIRECTORY_2026)).toBe("Nyck de Vries");
    expect(driverLabel({ name: "Kimi Antonelli" }, "code")).toBe("Kimi Antonelli");
    expect(driverLabel({ name: "Ryō Hirakawa", code: "HIR" }, "codeLast")).toBe("Ryō Hirakawa HIR");
    expect(driverLabel({ name: "Ryō Hirakawa", lastName: "Hirakawa" }, "codeLast")).toBe("Hirakawa");
  });

  it("never shortens a champion's name: Juan Manuel Fangio is Fangio or Juan Manuel Fangio, never Juan Fangio", () => {
    const drivers = CHAMPION_STATS.most_driver_titles ?? [];
    const labels = drivers.map((entry) => ({
      full: driverLabel({ name: entry.name, lastName: entry.last_name }, "full"),
      last: driverLabel({ name: entry.name, lastName: entry.last_name }, "last"),
    }));

    expect(labels.slice(0, 3)).toEqual([
      { full: "Lewis Hamilton", last: "Hamilton" },
      { full: "Michael Schumacher", last: "Schumacher" },
      { full: "Juan Manuel Fangio", last: "Fangio" },
    ]);
    expect(labels.flatMap(({ full, last }) => [full, last])).not.toContain("Juan Fangio");
  });

  it("prints f1db's names, never the legal full names the champions query once read", () => {
    const names = (CHAMPION_STATS.most_driver_titles ?? []).map((entry) => entry.name);
    // f1db v2026.19.0 `driver.full_name` for six of these champions.
    const legal = [
      "Juan Manuel Fangio Déramo",
      "Lewis Carl Davidson Hamilton",
      "Ayrton Senna da Silva",
      "Fernando Alonso Díaz",
      "Max Emilian Verstappen",
      "Nelson Piquet Souto Maior",
    ];

    expect(names).toEqual(expect.arrayContaining(["Juan Manuel Fangio", "Lewis Hamilton", "Ayrton Senna"]));
    expect(names.filter((name) => legal.includes(name))).toEqual([]);
  });

  it("labels a constructor row, which has no surname, by its name", () => {
    const [ferrari] = CHAMPION_STATS.most_constructor_titles ?? [];
    expect(driverLabel({ name: ferrari.name, lastName: ferrari.last_name }, "last")).toBe("Ferrari");
  });
});

describe("findDirectoryTeam", () => {
  it("finds this season's team by id, f1db name, full name or a feed's alias, never a substring", () => {
    expect(findDirectoryTeam(DIRECTORY_2026, { name: "", id: "haas" })?.name).toBe("Haas");
    expect(findDirectoryTeam(DIRECTORY_2026, { name: "Racing Bulls" })?.id).toBe("racing-bulls");
    expect(findDirectoryTeam(DIRECTORY_2026, { name: "Mercedes AMG F1" })?.id).toBe("mercedes");
    expect(findDirectoryTeam(DIRECTORY_2026, { name: openF1Team("BEA") })?.id).toBe("haas");
    expect(findDirectoryTeam(DIRECTORY_2026, { name: "Red" })).toBeNull();
    expect(findDirectoryTeam(DIRECTORY_2026, { id: "lotus" })).toBeNull();
  });

  it("reads no row of another season against this season's list", () => {
    expect(findDirectoryTeam(DIRECTORY_2026, { name: "Haas F1 Team", year: 2023 })).toBeNull();
    expect(findDirectoryTeam(undefined, { name: "Haas" })).toBeNull();
  });
});

describe("teamLabel", () => {
  it("prints f1db's name for a feed's spelling of a team on this season's grid", () => {
    expect(teamLabel({ name: openF1Team("BEA") }, "name", DIRECTORY_2026)).toBe("Haas");
    expect(teamLabel({ name: openF1Team("VER") }, "name", DIRECTORY_2026)).toBe("Red Bull");
    expect(teamLabel({ name: openF1Team("LAW") }, "name", DIRECTORY_2026)).toBe("Racing Bulls");
  });

  it("prints the full name from the payload, else from the directory", () => {
    expect(teamLabel({ name: "Red Bull", fullName: "Oracle Red Bull Racing" }, "full", DIRECTORY_2026)).toBe(
      "Oracle Red Bull Racing",
    );
    expect(teamLabel({ name: "Red Bull" }, "full", DIRECTORY_2026)).toBe("Red Bull Racing");
  });

  it("prints a team it cannot place exactly as the payload spells it", () => {
    expect(teamLabel({ name: "Haas F1 Team" }, "name")).toBe("Haas F1 Team");
    expect(teamLabel({ name: "Haas F1 Team" }, "full")).toBe("Haas F1 Team");
    expect(teamLabel({ name: "Lotus", year: 1973 }, "full", DIRECTORY_2026)).toBe("Lotus");
  });
});
