import SwiftUI

struct TimingTower: View {
    let positions: [LivePosition]
    let sessionStatus: SessionStatus?

    var body: some View {
        VStack(spacing: 2) {
            // Session info header
            if let status = sessionStatus {
                HStack {
                    if let lap = status.lap, let total = status.totalLaps {
                        Text("LAP \(lap)/\(total)")
                            .font(.system(size: 12, weight: .black, design: .monospaced))
                    }

                    Spacer()

                    Text(status.status.uppercased())
                        .font(.system(size: 10, weight: .bold))
                        .tracking(1)
                        .foregroundStyle(statusColor(status.status))
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
            }

            // Column headers
            HStack(spacing: 0) {
                Text("P").frame(width: 24, alignment: .leading)
                Text("DRIVER").frame(maxWidth: .infinity, alignment: .leading)
                Text("GAP").frame(width: 70, alignment: .trailing)
                Text("LAST").frame(width: 70, alignment: .trailing)
                Text("TYRE").frame(width: 36)
                Text("PIT").frame(width: 24, alignment: .trailing)
            }
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .padding(.bottom, 4)

            // Positions
            ForEach(positions) { pos in
                PositionRow(position: pos)
            }
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "started": return .green
        case "red flag": return .red
        case "safety car", "vsc": return .yellow
        case "finished": return .secondary
        default: return .primary
        }
    }
}
