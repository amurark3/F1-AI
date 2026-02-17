import SwiftUI

/// Renders a race result card as a shareable image.
struct ShareableResultCard: View {
    let raceName: String
    let year: Int
    let podium: [PodiumEntry]?
    let topResults: [RaceResult]

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 4) {
                Text("F1 AI")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(3)
                    .foregroundStyle(.red)

                Text(raceName.uppercased())
                    .font(.system(size: 20, weight: .black))
                    .italic()

                Text(String(year))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 16)
            .padding(.bottom, 12)

            // Podium
            if let podium, podium.count >= 3 {
                HStack(alignment: .bottom, spacing: 8) {
                    podiumBlock(podium[1], height: 50, label: "2ND")
                    podiumBlock(podium[0], height: 70, label: "1ST")
                    podiumBlock(podium[2], height: 36, label: "3RD")
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 12)
            }

            // Top 10 results
            VStack(spacing: 1) {
                ForEach(Array(topResults.prefix(10).enumerated()), id: \.offset) { _, result in
                    HStack(spacing: 0) {
                        Text(result.position.map(String.init) ?? "-")
                            .font(.system(size: 12, weight: .black))
                            .frame(width: 28, alignment: .leading)

                        Text(result.fullName)
                            .font(.system(size: 12, weight: .medium))
                            .lineLimit(1)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Text(result.time.isEmpty ? "-" : result.time)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 80, alignment: .trailing)

                        if result.points > 0 {
                            Text(String(format: "%.0f", result.points))
                                .font(.system(size: 11, weight: .bold))
                                .frame(width: 28, alignment: .trailing)
                        } else {
                            Text("")
                                .frame(width: 28)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                }
            }
            .padding(.vertical, 8)

            // Footer
            Text("Shared from F1 AI")
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .padding(.bottom, 12)
        }
        .frame(width: 320)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func podiumBlock(_ entry: PodiumEntry, height: CGFloat, label: String) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.secondary)
            Text(entry.driver)
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(.red)
            Text(entry.team)
                .font(.system(size: 8))
                .foregroundStyle(.secondary)

            RoundedRectangle(cornerRadius: 6)
                .fill(Color.secondary.opacity(0.15))
                .frame(height: height)
                .overlay {
                    Text(String(entry.position))
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(.secondary.opacity(0.3))
                }
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Image Renderer Extension

extension ShareableResultCard {
    @MainActor
    func renderImage() -> UIImage? {
        let renderer = ImageRenderer(content: self.preferredColorScheme(.dark))
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
    }
}

/// A share button that renders the card and presents a share sheet.
struct ShareResultButton: View {
    let raceName: String
    let year: Int
    let podium: [PodiumEntry]?
    let results: [RaceResult]

    @State private var shareImage: UIImage?
    @State private var showShare = false

    var body: some View {
        Button {
            let card = ShareableResultCard(
                raceName: raceName,
                year: year,
                podium: podium,
                topResults: results
            )
            shareImage = card.renderImage()
            if shareImage != nil {
                showShare = true
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 12))
                Text("Share")
                    .font(.system(size: 12, weight: .bold))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.ultraThinMaterial, in: Capsule())
        }
        .sheet(isPresented: $showShare) {
            if let image = shareImage {
                ShareSheet(items: [image])
            }
        }
    }
}

/// UIKit share sheet wrapper.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
