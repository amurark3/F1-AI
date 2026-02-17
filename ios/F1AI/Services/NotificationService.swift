import Foundation
import UserNotifications

final class NotificationService {
    static let shared = NotificationService()

    private init() {}

    func requestPermission() async -> Bool {
        do {
            return try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
        } catch {
            return false
        }
    }

    /// Schedules race session reminders (30 min and 5 min before).
    func scheduleRaceReminders(for race: RaceEvent) {
        let center = UNUserNotificationCenter.current()

        // Remove existing notifications for this round
        let prefix = "race-\(race.round)"
        center.removePendingNotificationRequests(withIdentifiers: [
            "\(prefix)-30", "\(prefix)-5"
        ])

        guard let raceTimeStr = race.sessions["Race"],
              let raceDate = ISO8601DateFormatter().date(from: raceTimeStr) ?? parseFlexibleDate(raceTimeStr)
        else { return }

        let offsets: [(minutes: Int, id: String, body: String)] = [
            (30, "\(prefix)-30", "\(race.name) starts in 30 minutes!"),
            (5, "\(prefix)-5", "\(race.name) is about to start!"),
        ]

        for offset in offsets {
            guard let triggerDate = Calendar.current.date(byAdding: .minute, value: -offset.minutes, to: raceDate),
                  triggerDate > Date()
            else { continue }

            let content = UNMutableNotificationContent()
            content.title = "F1 AI"
            content.body = offset.body
            content.sound = .default

            let components = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: triggerDate
            )
            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)

            let request = UNNotificationRequest(identifier: offset.id, content: content, trigger: trigger)
            center.add(request)
        }
    }

    private func parseFlexibleDate(_ string: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: string) { return date }

        // Try without timezone (backend sometimes omits Z)
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: string + "Z") { return date }

        return nil
    }
}
