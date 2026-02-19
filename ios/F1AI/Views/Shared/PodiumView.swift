import SwiftUI

struct PodiumView: View {
    let podium: [PodiumEntry]

    var body: some View {
        if podium.count >= 3 {
            HStack(alignment: .bottom, spacing: 8) {
                // P2 — left
                podiumStep(entry: podium[1], height: 80, label: "2ND")
                // P1 — center, tallest
                podiumStep(entry: podium[0], height: 110, label: "1ST")
                // P3 — right
                podiumStep(entry: podium[2], height: 64, label: "3RD")
            }
            .padding(.horizontal)
        }
    }

    @ViewBuilder
    private func podiumStep(entry: PodiumEntry, height: CGFloat, label: String) -> some View {
        let teamColor = TeamColor.color(for: entry.team)

        VStack(spacing: 4) {
            Text(label)
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            Text(entry.driver)
                .font(.system(size: 18, weight: .black))
                .foregroundStyle(teamColor)

            Text(entry.team)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(1)

            RoundedRectangle(cornerRadius: 12)
                .fill(
                    LinearGradient(
                        colors: [teamColor.opacity(0.15), teamColor.opacity(0.05)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(teamColor.opacity(0.3), lineWidth: 1)
                        .padding(.bottom, -1) // Only top border visible
                        .clipped()
                )
                .frame(height: height)
                .overlay {
                    Text("\(entry.position)")
                        .font(.system(size: 28, weight: .black))
                        .foregroundStyle(.white.opacity(0.15))
                }
        }
        .frame(maxWidth: .infinity)
    }
}
