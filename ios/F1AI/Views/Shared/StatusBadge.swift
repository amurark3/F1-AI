import SwiftUI

struct StatusBadge: View {
    let status: RaceStatus

    var body: some View {
        Text(status.label.uppercased())
            .font(.system(size: 10, weight: .bold))
            .tracking(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(background)
            .foregroundStyle(foregroundColor)
            .clipShape(Capsule())
    }

    private var background: some ShapeStyle {
        switch status {
        case .completed:
            return AnyShapeStyle(.ultraThinMaterial)
        case .inProgress:
            return AnyShapeStyle(
                LinearGradient(
                    colors: [.red, .orange],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
        case .upcoming:
            return AnyShapeStyle(.ultraThinMaterial)
        }
    }

    private var foregroundColor: Color {
        switch status {
        case .completed: return .secondary
        case .inProgress: return .white
        case .upcoming: return .primary
        }
    }
}
