import Foundation

@Observable
final class RaceDetailViewModel {
    var detail: RaceDetailResponse?
    var isLoading = false
    var error: String?
    var selectedTab: ResultTab = .race

    private let api = APIClient.shared

    enum ResultTab: String, CaseIterable {
        case race = "Race"
        case qualifying = "Quali"
        case sprint = "Sprint"
        case sprintQuali = "SQ"

        /// The session key in the `sessions` dict that maps to this tab
        var sessionKey: String {
            switch self {
            case .race: return "Race"
            case .qualifying: return "Qualifying"
            case .sprint: return "Sprint"
            case .sprintQuali: return "Sprint Qualifying"
            }
        }
    }

    enum TabStatus {
        case available   // session done, data exists
        case empty       // session done, no data from API
        case locked      // session hasn't happened yet
    }

    var availableTabs: [ResultTab] {
        var tabs: [ResultTab] = [.race, .qualifying]
        if detail?.isSprint == true {
            tabs.append(contentsOf: [.sprint, .sprintQuali])
        }
        return tabs
    }

    /// Determine the status of a result tab based on session time and available data
    func tabStatus(for tab: ResultTab, sessions: [String: String]) -> TabStatus {
        // Check if session time is in the future → locked
        if let timeStr = sessions[tab.sessionKey], let date = parseDate(timeStr) {
            if date > Date() {
                return .locked
            }
        }

        // Session is in the past (or no time info) — check if we have data
        guard let detail else { return .empty }

        let hasData: Bool
        switch tab {
        case .race:
            hasData = detail.raceResults?.isEmpty == false
        case .qualifying:
            hasData = detail.qualifying?.values.contains(where: { !$0.isEmpty }) == true
        case .sprint:
            hasData = detail.sprintResults?.isEmpty == false
        case .sprintQuali:
            hasData = detail.sprintQualifying?.values.contains(where: { !$0.isEmpty }) == true
        }

        return hasData ? .available : .empty
    }

    /// Check if any session is currently live (started within last ~3 hours)
    func isSessionLive(sessions: [String: String]) -> Bool {
        let now = Date()
        for (_, timeStr) in sessions {
            guard let date = parseDate(timeStr) else { continue }
            // Session started and within a reasonable window (3 hours)
            if date < now && now.timeIntervalSince(date) < 3 * 3600 {
                return true
            }
        }
        return false
    }

    func loadDetail(year: Int, round: Int, sessions: [String: String] = [:]) async {
        isLoading = true
        error = nil
        do {
            detail = try await api.fetchRaceDetail(year: year, round: round)
            if let err = detail?.error {
                self.error = err
            }
            // Auto-select the first non-locked tab
            selectFirstAvailableTab(sessions: sessions)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    /// Select the first tab that isn't locked
    private func selectFirstAvailableTab(sessions: [String: String]) {
        for tab in availableTabs {
            if tabStatus(for: tab, sessions: sessions) != .locked {
                selectedTab = tab
                return
            }
        }
        // All locked — just pick the first one
        if let first = availableTabs.first {
            selectedTab = first
        }
    }

    func retry(year: Int, round: Int) {
        Task { await loadDetail(year: year, round: round) }
    }

    private func parseDate(_ str: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        return iso.date(from: str) ?? iso.date(from: str + "Z")
    }
}
