import Foundation

@MainActor
@Observable
final class StandingsViewModel {
    var drivers: [DriverStanding] = []
    var constructors: [ConstructorStanding] = []
    var selectedYear: Int
    /// The year whose data is actually displayed (may differ from selectedYear if data is unavailable)
    var displayYear: Int
    var isUsingFallback = false
    var showingDrivers = true
    var isLoading = false
    var error: String?

    private let api = APIClient.shared

    init() {
        let year = Calendar.current.component(.year, from: Date())
        self.selectedYear = year
        self.displayYear = year
    }

    func loadStandings() async {
        isLoading = true
        error = nil
        isUsingFallback = false
        do {
            async let d = api.fetchDriverStandings(year: selectedYear)
            async let c = api.fetchConstructorStandings(year: selectedYear)
            let fetchedDrivers = try await d
            let fetchedConstructors = try await c

            if fetchedDrivers.isEmpty && selectedYear == Calendar.current.component(.year, from: Date()) {
                // Current year not available yet — fall back to previous year
                let fallback = selectedYear - 1
                async let fd = api.fetchDriverStandings(year: fallback)
                async let fc = api.fetchConstructorStandings(year: fallback)
                drivers = try await fd
                constructors = try await fc
                displayYear = fallback
                isUsingFallback = true
            } else {
                drivers = fetchedDrivers
                constructors = fetchedConstructors
                displayYear = selectedYear
            }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func changeYear(_ year: Int) {
        selectedYear = year
        drivers = []
        constructors = []
        Task { await loadStandings() }
    }
}
