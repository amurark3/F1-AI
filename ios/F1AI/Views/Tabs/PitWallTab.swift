import SwiftUI

struct PitWallTab: View {
    @State private var vm = ChatViewModel()
    @State private var serverStatus = ServerStatusService.shared

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if serverStatus.status == .warming {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Warming up server...")
                            .font(.system(size: 13))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(.ultraThinMaterial)
                }
                ChatView(vm: vm)
            }
            .navigationTitle("Pit Wall")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if !vm.messages.isEmpty {
                        Button("Clear", role: .destructive) {
                            vm.clearHistory()
                        }
                        .font(.system(size: 13))
                    }
                }
            }
            .task {
                serverStatus.startPolling()
            }
        }
    }
}
