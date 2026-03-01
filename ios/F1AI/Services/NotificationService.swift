import Foundation
import UserNotifications

final class NotificationService {
    static let shared = NotificationService()
    private init() {}

    // MARK: - Session name mapping

    /// Backend session keys (from RaceEvent.sessions dict) → user-facing names for notification body
    static let sessionDisplayNames: [String: String] = [
        "Practice 1":        "FP1",
        "Practice 2":        "FP2",
        "Practice 3":        "FP3",
        "Sprint Qualifying": "Sprint Qualifying",
        "Sprint":            "Sprint Race",
        "Qualifying":        "Qualifying",
        "Race":              "",        // "Monaco Grand Prix starts in 15 minutes" (no session label)
    ]

    /// All session keys in display order
    static let allSessionKeys: [String] = [
        "Practice 1", "Practice 2", "Practice 3",
        "Qualifying", "Sprint Qualifying", "Sprint", "Race"
    ]

    // MARK: - Permission

    func requestPermission() async -> Bool {
        do {
            return try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
        } catch {
            return false
        }
    }

    // MARK: - Schedule all sessions

    /// Schedules notifications for all enabled sessions in a race event.
    /// Removes any previously scheduled notifications for this round first (prevents duplicates).
    func scheduleSessionReminders(for race: RaceEvent) {
        let center = UNUserNotificationCenter.current()
        let prefix = "race-\(race.round)"
        let enabledSessions = UserDefaults.standard.enabledNotificationSessions
        let advanceMinutes = UserDefaults.standard.notificationAdvanceMinutes

        // Remove all existing pending notifications for this round (any advance time, any session)
        // Use a prefix pattern: get all pending, filter by prefix, remove matching
        center.getPendingNotificationRequests { pending in
            let toRemove = pending.map(\.identifier).filter { $0.hasPrefix(prefix) }
            if !toRemove.isEmpty {
                center.removePendingNotificationRequests(withIdentifiers: toRemove)
            }

            // Schedule new notifications for enabled sessions
            for (sessionKey, timeStr) in race.sessions {
                guard enabledSessions.contains(sessionKey) else { continue }

                let iso = ISO8601DateFormatter()
                iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                var sessionDate = iso.date(from: timeStr)
                if sessionDate == nil {
                    iso.formatOptions = [.withInternetDateTime]
                    sessionDate = iso.date(from: timeStr) ?? iso.date(from: timeStr + "Z")
                }
                guard let date = sessionDate,
                      let triggerDate = Calendar.current.date(
                          byAdding: .minute, value: -advanceMinutes, to: date),
                      triggerDate > Date()
                else { continue }

                let content = UNMutableNotificationContent()
                content.title = "F1 AI"
                let displayName = NotificationService.sessionDisplayNames[sessionKey] ?? sessionKey
                if displayName.isEmpty {
                    // Race: "Monaco Grand Prix starts in 15 minutes"
                    content.body = "\(race.name) starts in \(advanceMinutes) minutes"
                } else {
                    // Sessions: "Monaco Grand Prix FP1 starts in 15 minutes"
                    content.body = "\(race.name) \(displayName) starts in \(advanceMinutes) minutes"
                }
                content.sound = .default

                let components = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute], from: triggerDate)
                let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
                // Identifier includes advance time so changing settings creates new IDs (previous ones already cleared above)
                let id = "\(prefix)-\(sessionKey)-\(advanceMinutes)"
                let request = UNNotificationRequest(identifier: id, content: content, trigger: trigger)
                center.add(request)
            }
        }
    }

    /// Reschedule all notifications for an array of races (e.g., after settings change).
    func rescheduleAll(for races: [RaceEvent]) {
        for race in races {
            scheduleSessionReminders(for: race)
        }
    }

    // MARK: - Backward compatibility shim

    /// Legacy method — preserved for any existing callers. Delegates to scheduleSessionReminders.
    func scheduleRaceReminders(for race: RaceEvent) {
        scheduleSessionReminders(for: race)
    }
}

// MARK: - UserDefaults extensions for notification settings

extension UserDefaults {
    /// Which session types the user wants notifications for. Defaults to all sessions.
    var enabledNotificationSessions: Set<String> {
        get {
            let arr = array(forKey: "notificationEnabledSessions") as? [String]
            return Set(arr ?? NotificationService.allSessionKeys)
        }
        set {
            set(Array(newValue), forKey: "notificationEnabledSessions")
        }
    }

    /// How many minutes before session start to notify. Options: 5, 15, 30. Default: 15.
    var notificationAdvanceMinutes: Int {
        get {
            let stored = integer(forKey: "notificationAdvanceMinutes")
            return [5, 15, 30].contains(stored) ? stored : 15
        }
        set {
            set(newValue, forKey: "notificationAdvanceMinutes")
        }
    }
}
