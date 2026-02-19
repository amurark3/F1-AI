import SwiftUI

struct PitWallTab: View {
    @State private var vm = ChatViewModel()

    var body: some View {
        NavigationStack {
            ChatView(vm: vm)
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
        }
    }
}
