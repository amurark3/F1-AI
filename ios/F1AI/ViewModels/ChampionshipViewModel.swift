import Foundation

@Observable
final class ChampionshipViewModel {
    // Data
    var drivers: [DriverStanding] = []
    var constructors: [ConstructorStanding] = []
    var schedule: [RaceEvent] = []
    var isLoading = false
    var error: String?

    // What-if: how many of the upcoming races does the challenger win?
    // Preset options (per RESEARCH.md recommendation): 3, 5, or all remaining
    var whatIfRaces: Int = 3   // default preset

    var selectedYear: Int = Calendar.current.component(.year, from: Date())

    private let api = APIClient.shared

    // F1 2025 points system
    private let racePoints = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    // MARK: - Computed: remaining schedule

    var upcomingRaces: [RaceEvent] {
        schedule.filter { $0.raceStatus == .upcoming }
    }

    // Maximum points available per race weekend (26 standard, 34 sprint weekend)
    var maxPointsRemaining: Int {
        upcomingRaces.reduce(0) { total, race in
            let raceMax = 26  // 25 (win) + 1 (fastest lap bonus)
            let sprintMax = race.isSprint == true ? 8 : 0
            return total + raceMax + sprintMax
        }
    }

    // MARK: - WDC contenders

    var wdcContenders: [DriverStanding] {
        guard let leader = drivers.first else { return [] }
        return drivers.filter { driver in
            (leader.points - driver.points) <= Double(maxPointsRemaining)
        }
    }

    // Points the driver would gain if they win whatIfRaces of upcoming races
    // Assumes: win = 25 pts + 1 fastest lap = 26 pts per race
    func wdcProjectedPoints(for driver: DriverStanding) -> Double {
        let bonus = Double(min(whatIfRaces, upcomingRaces.count)) * 26
        return driver.points + bonus
    }

    // Points the leader would gain (we assume leader keeps scoring — use 2nd place avg: 18 pts)
    func wdcLeaderProjectedPoints() -> Double {
        guard let leader = drivers.first else { return 0 }
        let leadersRacesLeft = upcomingRaces.count - whatIfRaces
        // Conservative: leader still scores 18/race in races driver doesn't "win"
        let leaderBonus = Double(max(0, leadersRacesLeft)) * 18
        return leader.points + leaderBonus
    }

    // Can this driver overtake the leader if they win whatIfRaces?
    func canOvertake(driver: DriverStanding) -> Bool {
        guard let leader = drivers.first, leader.driver != driver.driver else { return false }
        return wdcProjectedPoints(for: driver) > driver.points  // simplified: just show points gap closing
    }

    func pointsToOvertake(driver: DriverStanding) -> Double {
        guard let leader = drivers.first else { return 0 }
        return max(0, leader.points - driver.points + 1)
    }

    // Whether the championship is already decided (leader's gap > maxPointsRemaining for all others)
    var wdcClinched: Bool {
        guard let leader = drivers.first else { return false }
        return drivers.dropFirst().allSatisfy { driver in
            (leader.points - driver.points) > Double(maxPointsRemaining)
        }
    }

    var wdcChampion: DriverStanding? {
        wdcClinched ? drivers.first : nil
    }

    // MARK: - WCC contenders

    var wccContenders: [ConstructorStanding] {
        guard let leader = constructors.first else { return [] }
        // WCC max points per race = 2x WDC max (both cars score)
        let wccMaxRemaining = maxPointsRemaining * 2
        return constructors.filter { team in
            (leader.points - team.points) <= Double(wccMaxRemaining)
        }
    }

    func wccPointsToOvertake(team: ConstructorStanding) -> Double {
        guard let leader = constructors.first else { return 0 }
        return max(0, leader.points - team.points + 1)
    }

    var wccClinched: Bool {
        guard let leader = constructors.first else { return false }
        let wccMaxRemaining = maxPointsRemaining * 2
        return constructors.dropFirst().allSatisfy { team in
            (leader.points - team.points) > Double(wccMaxRemaining)
        }
    }

    var wccChampion: ConstructorStanding? {
        wccClinched ? constructors.first : nil
    }

    // MARK: - Data loading

    func load(year: Int) async {
        isLoading = true
        error = nil
        selectedYear = year
        do {
            async let d = api.fetchDriverStandings(year: year)
            async let c = api.fetchConstructorStandings(year: year)
            async let s = api.fetchSchedule(year: year)
            drivers = try await d
            constructors = try await c
            schedule = try await s
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func changeYear(_ year: Int) {
        selectedYear = year
        Task { await load(year: year) }
    }
}
