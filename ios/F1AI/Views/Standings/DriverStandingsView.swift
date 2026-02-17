import SwiftUI

struct DriverStandingsView: View {
    let drivers: [DriverStanding]

    var body: some View {
        if drivers.isEmpty {
            ContentUnavailableView("No standings data", systemImage: "trophy")
        } else {
            LazyVStack(spacing: 2) {
                // Header
                HStack(spacing: 0) {
                    Text("POS").frame(width: 36, alignment: .leading)
                    Text("DRIVER").frame(maxWidth: .infinity, alignment: .leading)
                    Text("TEAM").frame(width: 100, alignment: .leading)
                    Text("WINS").frame(width: 40)
                    Text("PTS").frame(width: 50, alignment: .trailing)
                }
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.bottom, 4)

                ForEach(drivers) { driver in
                    let teamColor = TeamColor.color(for: driver.team)

                    HStack(spacing: 0) {
                        Text("\(driver.position)")
                            .font(.system(size: 14, weight: .black))
                            .foregroundStyle(driver.position <= 3 ? .primary : .secondary)
                            .frame(width: 36, alignment: .leading)

                        HStack(spacing: 6) {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(teamColor)
                                .frame(width: 3, height: 16)

                            Text(driver.driver)
                                .font(.system(size: 13, weight: .medium))
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Text(driver.team)
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .frame(width: 100, alignment: .leading)

                        Text(driver.wins > 0 ? "\(driver.wins)" : "-")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(driver.wins > 0 ? .orange : .secondary)
                            .frame(width: 40)

                        Text(String(format: "%.0f", driver.points))
                            .font(.system(size: 13, weight: .black))
                            .frame(width: 50, alignment: .trailing)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(
                        driver.position <= 3 ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(.clear),
                        in: RoundedRectangle(cornerRadius: 8)
                    )
                }
            }
        }
    }
}
