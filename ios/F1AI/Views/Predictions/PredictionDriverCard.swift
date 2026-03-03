import SwiftUI

struct PredictionDriverCard: View {
    let prediction: DriverPrediction
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // --- Always visible header ---
            HStack(alignment: .center, spacing: 12) {
                // Position badge
                Text("\(prediction.position)")
                    .font(.system(size: 18, weight: .black, design: .monospaced))
                    .foregroundStyle(prediction.position <= 3 ? .white : .secondary)
                    .frame(width: 28, alignment: .center)

                // Driver name + team
                VStack(alignment: .leading, spacing: 2) {
                    Text(prediction.driverName)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(.primary)
                    Text(prediction.team)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(TeamColor.color(for: prediction.team))
                }

                Spacer()

                // Confidence range — this is the "win probability" shown on the card
                VStack(alignment: .trailing, spacing: 2) {
                    Text(prediction.confidenceRange)
                        .font(.system(size: 13, weight: .black, design: .monospaced))
                        .foregroundStyle(.white)
                    Text("confidence")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .tracking(0.5)
                }

                // Expand chevron
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
                    .animation(.spring(response: 0.3, dampingFraction: 0.8), value: isExpanded)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                    isExpanded.toggle()
                }
            }

            // --- Expandable section: factors ---
            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Divider().opacity(0.15)
                        .padding(.horizontal, 14)

                    ForEach(prediction.factors.prefix(3), id: \.self) { factor in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(TeamColor.color(for: prediction.team))
                                .padding(.top, 2)
                            Text(factor)
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.horizontal, 14)
                    }
                }
                .padding(.bottom, 12)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(TeamColor.color(for: prediction.team).opacity(0.08))
                )
        )
        .overlay(
            // Left accent bar using team colour
            HStack {
                RoundedRectangle(cornerRadius: 2)
                    .fill(TeamColor.color(for: prediction.team))
                    .frame(width: 3)
                    .padding(.vertical, 6)
                Spacer()
            }
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
