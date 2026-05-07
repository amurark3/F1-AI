import SwiftUI

struct ChampionshipDriverRow: View {
    let standing: DriverStanding
    let pointsNeeded: Double
    let maxRemaining: Int
    let isLeader: Bool

    var body: some View {
        HStack(spacing: 12) {
            // Position
            Text("\(standing.position)")
                .font(.system(size: 16, weight: .black, design: .monospaced))
                .foregroundStyle(isLeader ? .white : .secondary)
                .frame(width: 24)

            // Driver + team
            VStack(alignment: .leading, spacing: 2) {
                Text(standing.driver)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.primary)
                Text(standing.team)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            // Points info
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(Int(standing.points)) pts")
                    .font(.system(size: 13, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                if !isLeader {
                    Text("-\(Int(pointsNeeded)) to lead")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.red.opacity(0.8))
                } else {
                    Text("Leader")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.green)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct ChampionshipConstructorRow: View {
    let standing: ConstructorStanding
    let pointsNeeded: Double
    let isLeader: Bool

    var body: some View {
        HStack(spacing: 12) {
            Text("\(standing.position)")
                .font(.system(size: 16, weight: .black, design: .monospaced))
                .foregroundStyle(isLeader ? .white : .secondary)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(standing.team)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.primary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(Int(standing.points)) pts")
                    .font(.system(size: 13, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                if !isLeader {
                    Text("-\(Int(pointsNeeded)) to lead")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.red.opacity(0.8))
                } else {
                    Text("Leader")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.green)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}
