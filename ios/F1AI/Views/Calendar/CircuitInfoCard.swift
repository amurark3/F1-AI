import SwiftUI

struct CircuitInfoCard: View {
    let circuit: CircuitInfo

    private static let kmToMiles = 0.621371

    private var trackLengthMiles: Double {
        circuit.trackLengthKm * Self.kmToMiles
    }

    private var totalDistanceMiles: String {
        String(format: "%.1f", Double(circuit.laps) * trackLengthMiles)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(circuit.circuitName)
                    .font(.system(size: 13, weight: .black))
                    .italic()

                Spacer()

                Text(circuit.circuitType.uppercased())
                    .font(.system(size: 9, weight: .bold))
                    .tracking(2)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 0) {
                Group {
                    Text("\(trackLengthMiles, specifier: "%.2f") mi")
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                    + Text(" x \(circuit.laps) laps = \(totalDistanceMiles) mi")
                        .foregroundStyle(.secondary)
                }
                .font(.system(size: 11))
            }

            HStack(spacing: 12) {
                HStack(spacing: 4) {
                    Text("Record:")
                        .foregroundStyle(.secondary)
                    Text(circuit.lapRecord.time)
                        .fontWeight(.bold)
                        .font(.system(.body, design: .monospaced))
                    if circuit.lapRecord.driver != "-" {
                        Text("(\(circuit.lapRecord.driver), \(String(circuit.lapRecord.year)))")
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 4) {
                    Text("Since")
                        .foregroundStyle(.secondary)
                    Text(String(circuit.firstGp))
                        .fontWeight(.bold)
                }
            }
            .font(.system(size: 11))
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
