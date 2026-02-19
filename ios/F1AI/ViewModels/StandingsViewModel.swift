import Foundation

@Observable
final class StandingsViewModel {
    var drivers: [DriverStanding] = []
    var constructors: [ConstructorStanding] = []
    var selectedYear: Int
    var showingDrivers = true
    var isLoading = false
    var error: String?

    private let api = APIClient.shared

    init() {
        let year = Calendar.current.component(.year, from: Date())
        self.selectedYear = year
    }

    func loadStandings() async {
        isLoading = true
        error = nil
        do {
            async let d = api.fetchDriverStandings(year: selectedYear)
            async let c = api.fetchConstructorStandings(year: selectedYear)
            drivers = try await d
            constructors = try await c
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func changeYear(_ year: Int) {
        selectedYear = year
        Task { await loadStandings() }
    }
}
