import SwiftUI

private struct SessionItem: Identifiable {
    let id: String
    let name: String
    let time: String

    init(name: String, time: String) {
        self.id = name
        self.name = name
        self.time = time
    }
}

struct SessionSchedule: View {
    let sessions: [String: String]

    private let sessionOrder = [
        "Practice 1", "Practice 2", "Practice 3",
        "Sprint Qualifying", "Sprint",
        "Qualifying", "Race"
    ]

    private var orderedSessions: [SessionItem] {
        sessionOrder.compactMap { name in
            sessions[name].map { SessionItem(name: name, time: $0) }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("SCHEDULE")
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            ForEach(orderedSessions) { session in
                let date = parseDate(session.time)
                let isDone = date.map { $0 < Date() } ?? false

                HStack {
                    Text(shortName(session.name))
                        .font(.system(size: 11, weight: .bold))
                        .tracking(1)
                        .foregroundStyle(sessionColor(name: session.name, isDone: isDone))
                        .strikethrough(isDone)
                        .frame(width: 60, alignment: .leading)

                    Spacer()

                    if let date {
                        Text(formatDay(date))
                            .font(.system(size: 11))
                            .foregroundStyle(Color.secondary.opacity(isDone ? 0.3 : 1.0))

                        Text(formatTime(date))
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .foregroundStyle(isDone ? Color.secondary.opacity(0.3) : Color.primary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background {
                                if !isDone {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(.ultraThinMaterial)
                                }
                            }
                    }
                }
            }
        }
    }

    private func sessionColor(name: String, isDone: Bool) -> Color {
        if isDone { return Color.secondary.opacity(0.4) }
        if name == "Race" { return .red }
        return .secondary
    }

    private func shortName(_ name: String) -> String {
        name.replacingOccurrences(of: "Practice 1", with: "FP1")
            .replacingOccurrences(of: "Practice 2", with: "FP2")
            .replacingOccurrences(of: "Practice 3", with: "FP3")
            .replacingOccurrences(of: "Sprint Qualifying", with: "SQ")
            .replacingOccurrences(of: "Qualifying", with: "QUALI")
            .replacingOccurrences(of: "Sprint", with: "SPRINT")
            .uppercased()
    }

    private func parseDate(_ str: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        return iso.date(from: str) ?? iso.date(from: str + "Z")
    }

    private func formatDay(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "EEE d MMM"
        return f.string(from: date).uppercased()
    }

    private func formatTime(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }
}
