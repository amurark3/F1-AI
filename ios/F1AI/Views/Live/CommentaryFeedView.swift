import SwiftUI

struct CommentaryFeedView: View {
    let entries: [CommentaryEntry]

    private func eventIcon(_ eventType: String) -> (name: String, color: Color) {
        switch eventType {
        case "safety_car":
            return ("exclamationmark.triangle.fill", .red)
        case "position_change":
            return ("arrow.up.arrow.down", .blue)
        case "pit_stop":
            return ("wrench.and.screwdriver.fill", .orange)
        default:
            return ("flag.fill", .gray)
        }
    }

    private func formattedTime(_ isoString: String) -> String {
        let isoFormatter = ISO8601DateFormatter()
        guard let date = isoFormatter.date(from: isoString) else { return isoString }
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }

    var body: some View {
        if entries.isEmpty {
            VStack(spacing: 8) {
                Image(systemName: "mic.slash")
                    .font(.system(size: 32))
                    .foregroundStyle(.secondary)
                Text("No commentary yet")
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(entries) { entry in
                        VStack(spacing: 0) {
                            HStack(alignment: .top, spacing: 12) {
                                let icon = eventIcon(entry.eventType)
                                Image(systemName: icon.name)
                                    .foregroundStyle(icon.color)
                                    .frame(width: 20)
                                    .padding(.top, 2)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(entry.text)
                                        .font(.system(size: 14))
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(formattedTime(entry.timestamp))
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                            Divider().padding(.leading, 48)
                        }
                    }
                }
            }
        }
    }
}
