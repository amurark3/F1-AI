import SwiftUI

struct RaceRow: View {
    let race: RaceEvent
    let countdown: String?

    var body: some View {
        HStack(spacing: 12) {
            // Round number
            Text("\(race.round)")
                .font(.system(size: 20, weight: .black, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 36)

            // Info
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(race.name.replacingOccurrences(of: "Grand Prix", with: "GP"))
                        .font(.system(size: 15, weight: .bold))
                        .lineLimit(1)

                    if race.isSprint == true {
                        Text("SPRINT")
                            .font(.system(size: 8, weight: .bold))
                            .tracking(1)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.yellow.opacity(0.15))
                            .foregroundStyle(.yellow)
                            .clipShape(Capsule())
                    }
                }

                Text(race.location)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            // Status / Countdown
            VStack(alignment: .trailing, spacing: 2) {
                StatusBadge(status: race.raceStatus)

                if let cd = countdown {
                    Text(cd)
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(.orange)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
