import SwiftUI

struct CountdownView: View {
    let countdown: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: "timer")
                .font(.title3)
                .foregroundStyle(.red)

            Text("LIGHTS OUT IN")
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            Text(countdown)
                .font(.system(size: 36, weight: .black, design: .rounded))
                .foregroundStyle(
                    LinearGradient(
                        colors: [.red, .orange],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
        }
        .padding(.vertical, 24)
        .frame(maxWidth: .infinity)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }
}
