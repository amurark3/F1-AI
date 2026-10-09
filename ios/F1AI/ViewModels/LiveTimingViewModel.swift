import Foundation
import UIKit

@Observable
final class LiveTimingViewModel {
    var service = LiveTimingService()
    var selectedSession = "Race"
    var previousPositions: [String: Int] = [:]

    let sessions = ["FP1", "FP2", "FP3", "Qualifying", "Race"]

    var isConnected: Bool { service.isConnected }
    var positions: [LivePosition] { service.positions }
    var sessionStatus: SessionStatus? { service.sessionStatus }
    var lastFlag: FlagEvent? { service.lastFlag }

    func connect(year: Int, round: Int) {
        // Store current positions before reconnect for delta detection
        previousPositions = Dictionary(
            uniqueKeysWithValues: service.positions.map { ($0.driver, $0.position) }
        )
        service.connect(baseURL: APIClient.shared.baseURL, year: year, round: round)
    }

    func disconnect() {
        service.disconnect()
    }

    /// Returns position change for haptic feedback.
    func positionDelta(for driver: String, currentPos: Int) -> Int? {
        guard let prev = previousPositions[driver] else { return nil }
        let delta = prev - currentPos
        return delta != 0 ? delta : nil
    }

    func triggerPositionHaptic(gained: Bool) {
        let generator = UIImpactFeedbackGenerator(style: gained ? .medium : .light)
        generator.impactOccurred()
    }

    func triggerFlagHaptic() {
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(.warning)
    }
}
