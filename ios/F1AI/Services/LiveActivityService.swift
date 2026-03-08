import ActivityKit
import Foundation

@Observable
final class LiveActivityService {
    private var currentActivity: Activity<RaceLiveActivityAttributes>?

    var isActive: Bool { currentActivity != nil }

    func startActivity(race: RaceEvent, positions: [LivePosition], sessionStatus: SessionStatus?) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        guard currentActivity == nil else { return }

        let tracked = resolveTrackedDriver(from: positions)
        let initialState = buildContentState(tracked: tracked, sessionStatus: sessionStatus)

        let year = Int(race.date?.prefix(4) ?? "2025") ?? 2025
        let attributes = RaceLiveActivityAttributes(raceName: race.name, round: race.round, year: year)

        do {
            currentActivity = try Activity.request(
                attributes: attributes,
                content: ActivityContent(state: initialState, staleDate: Date().addingTimeInterval(30))
            )
        } catch {
            print("LiveActivity start failed: \(error)")
        }
    }

    func update(positions: [LivePosition], sessionStatus: SessionStatus?) async {
        guard currentActivity != nil else { return }

        let tracked = resolveTrackedDriver(from: positions)
        let newState = buildContentState(tracked: tracked, sessionStatus: sessionStatus)

        await currentActivity?.update(
            ActivityContent(state: newState, staleDate: Date().addingTimeInterval(30))
        )
    }

    func endActivity(positions: [LivePosition], sessionStatus: SessionStatus?) async {
        let tracked = resolveTrackedDriver(from: positions)
        let finalState = buildContentState(tracked: tracked, sessionStatus: sessionStatus)

        let dismissal = ActivityUIDismissalPolicy.after(Date().addingTimeInterval(30 * 60))
        await currentActivity?.end(
            ActivityContent(state: finalState, staleDate: nil),
            dismissalPolicy: dismissal
        )
        currentActivity = nil
    }

    // MARK: - Private Helpers

    private func resolveTrackedDriver(from positions: [LivePosition]) -> LivePosition? {
        let fav = UserDefaults.standard.string(forKey: "favoriteDriver") ?? ""
        if fav.isEmpty {
            return positions.first
        }
        return positions.first(where: { $0.driver == fav }) ?? positions.first
    }

    private func buildContentState(tracked: LivePosition?, sessionStatus: SessionStatus?) -> RaceLiveActivityAttributes.ContentState {
        RaceLiveActivityAttributes.ContentState(
            trackedDriver: tracked?.driver ?? "",
            trackedPosition: tracked?.position ?? 1,
            trackedGap: tracked?.gap ?? "LEADER",
            currentLap: sessionStatus?.lap ?? 0,
            totalLaps: sessionStatus?.totalLaps ?? 0,
            sessionStatus: sessionStatus?.status ?? "started",
            isLeader: tracked?.position == 1
        )
    }
}
