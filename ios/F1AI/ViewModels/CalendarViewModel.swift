import Foundation

@Observable
final class CalendarViewModel {
    var schedule: [RaceEvent] = []
    var selectedYear: Int
    var isLoading = false
    var error: String?

    private let api = APIClient.shared

    init() {
        let now = Date()
        let month = Calendar.current.component(.month, from: now)
        let year = Calendar.current.component(.year, from: now)
        self.selectedYear = month >= 11 ? year + 1 : year
    }

    var currentRace: RaceEvent? {
        schedule.first { $0.status == "in_progress" }
            ?? schedule.first { $0.status == "upcoming" }
            ?? schedule.last
    }

    var completedCount: Int {
        schedule.filter { $0.status == "completed" }.count
    }

    func loadSchedule() async {
        isLoading = true
        error = nil
        do {
            schedule = try await api.fetchSchedule(year: selectedYear)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func changeYear(_ year: Int) {
        selectedYear = year
        Task { await loadSchedule() }
    }

    func countdown(for race: RaceEvent) -> String? {
        guard race.raceStatus == .upcoming,
              let raceTimeStr = race.sessions["Race"],
              let raceDate = parseDate(raceTimeStr)
        else { return nil }

        let diff = raceDate.timeIntervalSince(Date())
        guard diff > 0 else { return "NOW" }

        let days = Int(diff / 86400)
        let hours = Int((diff.truncatingRemainder(dividingBy: 86400)) / 3600)
        let mins = Int((diff.truncatingRemainder(dividingBy: 3600)) / 60)

        if days > 0 { return "\(days)d \(hours)h" }
        return "\(hours)h \(mins)m"
    }

    private func parseDate(_ str: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: str) { return d }
        return iso.date(from: str + "Z")
    }
}
