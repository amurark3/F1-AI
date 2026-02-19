import Foundation

@Observable
final class CompareViewModel {
    var comparison: CompareResponse?
    var isLoading = false
    var error: String?

    var driver1Input = ""
    var driver2Input = ""
    var selectedYear = Calendar.current.component(.year, from: Date())

    private let api = APIClient.shared

    // Common driver codes for quick selection
    static let popularDrivers = [
        "VER", "NOR", "LEC", "PIA", "HAM",
        "RUS", "SAI", "ALO", "GAS", "TSU",
        "STR", "HUL", "ANT", "HAD", "BEA",
        "LAW", "ALB", "COL", "DOO", "BOR",
    ]

    func compare() async {
        let d1 = driver1Input.trimmingCharacters(in: .whitespacesAndNewlines)
        let d2 = driver2Input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !d1.isEmpty, !d2.isEmpty else { return }

        isLoading = true
        error = nil
        comparison = nil

        do {
            let result = try await api.fetchComparison(year: selectedYear, driver1: d1, driver2: d2)
            if let err = result.error {
                self.error = err
            } else {
                comparison = result
            }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
