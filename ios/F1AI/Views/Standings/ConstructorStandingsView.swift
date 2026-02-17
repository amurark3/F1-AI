import SwiftUI

struct ConstructorStandingsView: View {
    let constructors: [ConstructorStanding]

    var body: some View {
        if constructors.isEmpty {
            ContentUnavailableView("No standings data", systemImage: "trophy")
        } else {
            LazyVStack(spacing: 2) {
                // Header
                HStack(spacing: 0) {
                    Text("POS").frame(width: 36, alignment: .leading)
                    Text("TEAM").frame(maxWidth: .infinity, alignment: .leading)
                    Text("WINS").frame(width: 40)
                    Text("PTS").frame(width: 60, alignment: .trailing)
                }
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.bottom, 4)

                ForEach(constructors) { team in
                    let teamColor = TeamColor.color(for: team.team)

                    HStack(spacing: 0) {
                        Text("\(team.position)")
                            .font(.system(size: 14, weight: .black))
                            .foregroundStyle(team.position <= 3 ? .primary : .secondary)
                            .frame(width: 36, alignment: .leading)

                        HStack(spacing: 8) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(teamColor)
                                .frame(width: 4, height: 20)

                            Text(team.team)
                                .font(.system(size: 14, weight: .semibold))
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Text(team.wins > 0 ? "\(team.wins)" : "-")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(team.wins > 0 ? .orange : .secondary)
                            .frame(width: 40)

                        Text(String(format: "%.0f", team.points))
                            .font(.system(size: 14, weight: .black))
                            .frame(width: 60, alignment: .trailing)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(
                        team.position <= 3 ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(.clear),
                        in: RoundedRectangle(cornerRadius: 8)
                    )
                }
            }
        }
    }
}
