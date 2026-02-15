"""
Championship scenario calculator.

Computes, for each completed round in a season, how many points per remaining
race a given driver would have needed to win the World Drivers' Championship.
Returns a Markdown table showing the progression.
"""

from fastf1.ergast import Ergast

# Maximum points a driver can score in a single race weekend.
# 25 (win) + 1 (fastest lap) + 8 (sprint win, if applicable) = 34
# Conservative estimate without sprint: 26
MAX_POINTS_PER_RACE = 26
MAX_POINTS_PER_SPRINT_WEEKEND = 34


def calculate_title_scenario(year: int, driver_name: str) -> str:
    """
    For each completed round in `year`, computes the points-per-remaining-race
    the specified driver would have needed to win the championship.

    `driver_name` can be a partial match (e.g., "Verstappen", "Norris").
    """
    ergast = Ergast()

    # Get the schedule to know total rounds.
    schedule = ergast.get_race_schedule(season=year)
    if schedule.empty:
        return f"No schedule data available for {year}."
    total_rounds = len(schedule)

    lines = [f"### Championship Scenario: {driver_name} ({year})\n"]
    lines.append("| After | Race | Driver Pts | Leader | Leader Pts | Gap | Remaining | Pts/Race Needed | Status |")
    lines.append("| :---- | :--- | :--------- | :----- | :--------- | :-- | :-------- | :-------------- | :----- |")

    found_any = False

    for rnd in range(1, total_rounds + 1):
        try:
            standings = ergast.get_driver_standings(season=year, round=rnd)
            if not standings.content:
                break
            df = standings.content[0]
        except Exception:
            break

        # Find the target driver (partial match on familyName).
        driver_row = df[df["familyName"].str.contains(driver_name, case=False, na=False)]
        if driver_row.empty:
            # Try givenName too.
            driver_row = df[df["givenName"].str.contains(driver_name, case=False, na=False)]
        if driver_row.empty:
            continue

        found_any = True
        driver_row = driver_row.iloc[0]
        driver_pts = float(driver_row["points"])
        driver_pos = int(driver_row["position"])

        # Leader info.
        leader = df.iloc[0]
        leader_pts = float(leader["points"])
        leader_name = f"{leader['givenName'][0]}. {leader['familyName']}"

        gap = leader_pts - driver_pts
        remaining = total_rounds - rnd

        # Get race name.
        race_name = schedule.iloc[rnd - 1].get("raceName", f"R{rnd}")
        race_name = race_name.replace("Grand Prix", "GP")

        if driver_pos == 1:
            status = "LEADING"
            pts_needed = "—"
        elif remaining == 0:
            status = "CHAMPION" if gap <= 0 else f"P{driver_pos} FINAL"
            pts_needed = "—"
        else:
            pts_per_race = gap / remaining
            if pts_per_race <= MAX_POINTS_PER_RACE:
                status = "Alive"
                pts_needed = f"{pts_per_race:.1f}"
            elif pts_per_race <= MAX_POINTS_PER_SPRINT_WEEKEND:
                status = "Needs sprints"
                pts_needed = f"{pts_per_race:.1f}"
            else:
                status = "ELIMINATED"
                pts_needed = f"{pts_per_race:.1f}"

        lines.append(
            f"| R{rnd} | {race_name} | {driver_pts:.0f} | "
            f"{leader_name} | {leader_pts:.0f} | {gap:.0f} | "
            f"{remaining} | {pts_needed} | {status} |"
        )

    if not found_any:
        return f"Could not find driver matching '{driver_name}' in the {year} standings."

    lines.append(
        f"\n*Max possible points per race: {MAX_POINTS_PER_RACE} (win + FL). "
        f"Sprint weekends allow up to {MAX_POINTS_PER_SPRINT_WEEKEND}.*"
    )
    return "\n".join(lines)
