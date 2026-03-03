import SwiftUI

/// Reusable toast/snackbar component.
/// Shown as a ZStack overlay at the bottom of the parent view.
/// Auto-dismisses after 4 seconds. Optional Retry action available during the window.
///
/// Usage:
///   ZStack(alignment: .bottom) {
///       mainContent
///       if let message = vm.toastMessage {
///           ToastView(message: message, onRetry: vm.retry, onDismiss: { vm.toastMessage = nil })
///               .padding(.bottom, 20)
///               .transition(.move(edge: .bottom).combined(with: .opacity))
///       }
///   }
///   .animation(.easeInOut(duration: 0.3), value: vm.toastMessage)
struct ToastView: View {
    let message: String
    let onRetry: (() -> Void)?
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.circle.fill")
                .foregroundStyle(.red)
                .font(.system(size: 16))

            Text(message)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.white)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)

            if let onRetry = onRetry {
                Button("Retry") {
                    onRetry()
                    onDismiss()
                }
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(.red)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.ultraThickMaterial, in: RoundedRectangle(cornerRadius: 14))
        .shadow(color: .black.opacity(0.3), radius: 12, y: 4)
        .padding(.horizontal, 16)
        .onAppear {
            // Auto-dismiss after 4 seconds (locked decision from CONTEXT.md)
            Task {
                try? await Task.sleep(for: .seconds(4))
                withAnimation(.easeInOut(duration: 0.3)) {
                    onDismiss()
                }
            }
        }
    }
}
