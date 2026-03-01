import Foundation

@Observable
final class PredictionsViewModel {
    var response: PredictionsResponse?
    var isLoading = false
    var error: String?          // network/decode error for first-load ContentUnavailableView
    var toastMessage: String?   // background refresh failure — shown in toast overlay
    var toastIsRetryable = true

    private let api = APIClient.shared

    // The current year and round — set by the parent view from schedule data
    var selectedYear: Int = Calendar.current.component(.year, from: Date())
    var selectedRound: Int = 0  // 0 = no upcoming race yet determined

    var predictions: [DriverPrediction] { response?.predictions ?? [] }

    var grandPrix: String { response?.grandPrix ?? "" }

    // Derived: true when there is no upcoming race (end of season or API says no race)
    var hasNoUpcomingRace: Bool {
        response?.error != nil || (response != nil && predictions.isEmpty)
    }

    // Call on first load (empty view — shows ContentUnavailableView on failure)
    func loadPredictions(year: Int, round: Int, isRefresh: Bool = false) async {
        if !isRefresh {
            isLoading = true
            error = nil
        }
        do {
            let result = try await api.fetchPredictions(year: year, round: round)
            response = result
            // Check for backend-level error (HTTP 200 with error body)
            if let backendError = result.error, !isRefresh {
                self.error = backendError
            }
        } catch {
            if isRefresh {
                // Background refresh failure — show toast, keep existing data
                toastMessage = "Failed to refresh predictions"
                toastIsRetryable = true
            } else {
                // First load failure — show ContentUnavailableView
                self.error = error.localizedDescription
            }
        }
        if !isRefresh { isLoading = false }
    }

    // Pull-to-refresh and toast retry both call this
    func retry() {
        guard selectedRound > 0 else { return }
        Task { await loadPredictions(year: selectedYear, round: selectedRound, isRefresh: true) }
    }

    func dismissToast() {
        toastMessage = nil
    }
}
