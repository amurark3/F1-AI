import WidgetKit
import SwiftUI

// MARK: - Data Model

struct NextRaceEntry: TimelineEntry {
    let date: Date
    let raceName: String
    let location: String
    let raceDate: Date?
    let round: Int
    let isSprint: Bool
}

// MARK: - Provider

struct NextRaceProvider: TimelineProvider {
    func placeholder(in context: Context) -> NextRaceEntry {
        NextRaceEntry(
            date: .now,
            raceName: "Australian Grand Prix",
            location: "Melbourne, Australia",
            raceDate: Date().addingTimeInterval(86400 * 7),
            round: 1,
            isSprint: false
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (NextRaceEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NextRaceEntry>) -> Void) {
        Task {
            let entry = await fetchNextRace()
            // Refresh every 30 minutes
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: 30, to: .now)!
            let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
            completion(timeline)
        }
    }

    private func fetchNextRace() async -> NextRaceEntry {
        let year = Calendar.current.component(.year, from: .now)
        guard let url = URL(string: "https://f1-ai.onrender.com/api/schedule/\(year)") else {
            return fallbackEntry
        }

        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let events = try JSONDecoder().decode([WidgetRaceEvent].self, from: data)

            // Find the next upcoming race
            let now = Date()
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime]

            for event in events {
                guard let dateStr = event.sessions["Race"],
                      let raceDate = iso.date(from: dateStr) ?? iso.date(from: dateStr + "Z")
                else { continue }

                if raceDate > now {
                    return NextRaceEntry(
                        date: .now,
                        raceName: event.name,
                        location: event.location,
                        raceDate: raceDate,
                        round: event.round,
                        isSprint: event.isSprint ?? false
                    )
                }
            }
        } catch {
            print("Widget fetch error: \(error)")
        }

        return NextRaceEntry(
            date: .now,
            raceName: "No upcoming race",
            location: "",
            raceDate: nil,
            round: 0,
            isSprint: false
        )
    }
}

// Minimal model for widget decoding
private struct WidgetRaceEvent: Codable {
    let round: Int
    let name: String
    let location: String
    let sessions: [String: String]
    let isSprint: Bool?

    enum CodingKeys: String, CodingKey {
        case round, name, location, sessions
        case isSprint = "is_sprint"
    }
}

extension NextRaceProvider {
    fileprivate var fallbackEntry: NextRaceEntry {
        NextRaceEntry(
            date: .now,
            raceName: "No upcoming race",
            location: "",
            raceDate: nil,
            round: 0,
            isSprint: false
        )
    }
}

// MARK: - Widget View

struct NextRaceWidgetView: View {
    let entry: NextRaceEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: "flag.checkered")
                    .font(.system(size: 10))
                    .foregroundStyle(.red)
                Text("ROUND \(entry.round)")
                    .font(.system(size: 9, weight: .bold))
                    .tracking(1)
                    .foregroundStyle(.red)

                Spacer()

                if entry.isSprint {
                    Text("SPRINT")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(.yellow)
                }
            }

            Text(entry.raceName.replacingOccurrences(of: "Grand Prix", with: "GP"))
                .font(.system(size: family == .systemSmall ? 14 : 16, weight: .black))
                .italic()
                .lineLimit(2)

            if !entry.location.isEmpty {
                Text(entry.location)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            if let raceDate = entry.raceDate {
                countdownView(to: raceDate)
            }
        }
        .containerBackground(.fill.tertiary, for: .widget)
    }

    private func countdownView(to date: Date) -> some View {
        let diff = date.timeIntervalSince(.now)
        let days = Int(diff / 86400)
        let hours = Int((diff.truncatingRemainder(dividingBy: 86400)) / 3600)

        return HStack(spacing: 8) {
            if days > 0 {
                countdownUnit(value: days, label: "DAYS")
            }
            countdownUnit(value: hours, label: "HRS")
        }
    }

    private func countdownUnit(value: Int, label: String) -> some View {
        VStack(spacing: 0) {
            Text(String(value))
                .font(.system(size: 22, weight: .black, design: .monospaced))
            Text(label)
                .font(.system(size: 8, weight: .bold))
                .tracking(1)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Widget Configuration

struct NextRaceWidget: Widget {
    let kind = "NextRaceWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: NextRaceProvider()) { entry in
            NextRaceWidgetView(entry: entry)
        }
        .configurationDisplayName("Next Race")
        .description("Countdown to the next F1 race.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Widget Bundle

@main
struct F1AIWidgets: WidgetBundle {
    var body: some Widget {
        NextRaceWidget()
    }
}
