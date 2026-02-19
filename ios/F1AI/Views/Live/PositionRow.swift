import SwiftUI

struct PositionRow: View {
    let position: LivePosition

    var body: some View {
        HStack(spacing: 0) {
            Text("\(position.position)")
                .font(.system(size: 12, weight: .black))
                .foregroundStyle(position.position <= 3 ? .primary : .secondary)
                .frame(width: 24, alignment: .leading)

            Text(position.driver)
                .font(.system(size: 13, weight: .bold, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(position.gap)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(position.position == 1 ? .primary : .secondary)
                .frame(width: 70, alignment: .trailing)

            Text(position.lastLap ?? "-")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 70, alignment: .trailing)

            tyreIndicator
                .frame(width: 36)

            Text(position.pitStops.map(String.init) ?? "-")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 24, alignment: .trailing)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(
            position.position <= 3 ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(.clear),
            in: RoundedRectangle(cornerRadius: 6)
        )
    }

    @ViewBuilder
    private var tyreIndicator: some View {
        if let tyre = position.tyre {
            Text(tyreAbbrev(tyre))
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.white)
                .padding(.horizontal, 4)
                .padding(.vertical, 2)
                .background(tyreColor(tyre), in: RoundedRectangle(cornerRadius: 3))
        } else {
            Text("-")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
    }

    private func tyreAbbrev(_ tyre: String) -> String {
        switch tyre.uppercased() {
        case "SOFT": return "S"
        case "MEDIUM": return "M"
        case "HARD": return "H"
        case "INTERMEDIATE": return "I"
        case "WET": return "W"
        default: return "?"
        }
    }

    private func tyreColor(_ tyre: String) -> Color {
        switch tyre.uppercased() {
        case "SOFT": return .red
        case "MEDIUM": return .yellow
        case "HARD": return .white.opacity(0.6)
        case "INTERMEDIATE": return .green
        case "WET": return .blue
        default: return .gray
        }
    }
}
