import ActivityKit
import WidgetKit
import SwiftUI

// MARK: - ActivityAttributes

struct RaceLiveActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var trackedDriver: String
        var trackedPosition: Int
        var trackedGap: String  // e.g. "LEADER" or "+3.4s"
        var currentLap: Int
        var totalLaps: Int
        var sessionStatus: String
        var isLeader: Bool
    }

    var raceName: String
    var round: Int
    var year: Int
}

// MARK: - Helpers

private func statusColor(_ status: String) -> Color {
    let lower = status.lowercased()
    if lower.contains("safety car") || lower.contains("red flag") {
        return .red
    } else if lower.contains("vsc") || lower.contains("virtual safety car") {
        return .yellow
    } else {
        return .white
    }
}

// MARK: - Live Activity Widget

struct RaceLiveActivityView: Widget {
    let kind = "RaceLiveActivity"

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RaceLiveActivityAttributes.self) { context in
            // Lock screen banner
            HStack {
                Text("P\(context.state.trackedPosition)")
                    .font(.system(size: 20, weight: .black))
                Text(context.state.trackedDriver)
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                Spacer()
                Text("LAP \(context.state.currentLap)/\(context.state.totalLaps)")
                    .font(.system(size: 12, design: .monospaced))
            }
            .padding()
            .activityBackgroundTint(Color.black)

        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded regions
                DynamicIslandExpandedRegion(.leading) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("P\(context.state.trackedPosition)")
                            .font(.system(size: 28, weight: .black))
                        Text(context.state.trackedDriver)
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("LAP \(context.state.currentLap)/\(context.state.totalLaps)")
                            .font(.system(size: 12, weight: .black, design: .monospaced))
                        Text(context.state.trackedGap)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(context.state.sessionStatus.uppercased())
                        .font(.system(size: 10, weight: .bold))
                        .tracking(1)
                        .foregroundStyle(statusColor(context.state.sessionStatus))
                }
            } compactLeading: {
                Text(context.state.trackedDriver)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
            } compactTrailing: {
                Text("P\(context.state.trackedPosition) L\(context.state.currentLap)")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
            } minimal: {
                Text("P\(context.state.trackedPosition)")
                    .font(.system(size: 11, weight: .black))
            }
        }
    }
}
