import SwiftUI

struct ChatView: View {
    @Bindable var vm: ChatViewModel
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        if vm.messages.isEmpty {
                            emptyState
                        }

                        ForEach(vm.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }

                        // Tool indicators
                        if !vm.activeTools.isEmpty {
                            toolIndicators
                        }
                    }
                    .padding()
                }
                .onChange(of: vm.messages.count) {
                    if let last = vm.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            Divider()

            // Input bar
            inputBar
        }
    }

    private static let suggestions: [(icon: String, text: String, query: String)] = [
        ("trophy.fill", "Last Race Results", "What were the results of the last race?"),
        ("list.number", "Championship Standings", "Show me the current driver standings"),
        ("person.2.fill", "Compare Drivers", "Compare Verstappen and Norris this season"),
        ("flag.checkered", "Next Race", "When and where is the next race?"),
        ("chart.line.uptrend.xyaxis", "Team Battle", "How are McLaren and Red Bull comparing this season?"),
        ("clock.arrow.circlepath", "Season Recap", "Summarize the season so far"),
    ]

    private var emptyState: some View {
        VStack(spacing: 20) {
            Image(systemName: "headphones")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)

            Text("Pit Wall")
                .font(.system(size: 20, weight: .black))
                .italic()

            Text("Your AI Race Engineer")
                .font(.system(size: 13))
                .foregroundStyle(.secondary)

            // Suggestion chips
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(Self.suggestions, id: \.text) { suggestion in
                    Button {
                        vm.inputText = suggestion.query
                        Task { await vm.send() }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: suggestion.icon)
                                .font(.system(size: 11))
                                .foregroundStyle(.red)

                            Text(suggestion.text)
                                .font(.system(size: 12, weight: .medium))
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
                    .foregroundStyle(.primary)
                }
            }
            .padding(.horizontal, 8)
        }
        .padding(.top, 60)
    }

    private var toolIndicators: some View {
        HStack(spacing: 8) {
            ForEach(vm.activeTools) { tool in
                HStack(spacing: 6) {
                    if tool.isActive {
                        ProgressView()
                            .scaleEffect(0.6)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(.green)
                    }

                    Text(tool.name)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(.ultraThinMaterial, in: Capsule())
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Ask your race engineer...", text: $vm.inputText, axis: .vertical)
                .font(.system(size: 14))
                .lineLimit(1...5)
                .focused($inputFocused)
                .textFieldStyle(.plain)
                .onSubmit { sendMessage() }

            Button {
                sendMessage()
            } label: {
                Image(systemName: vm.isStreaming ? "stop.circle.fill" : "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(
                        vm.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !vm.isStreaming
                            ? AnyShapeStyle(.secondary)
                            : AnyShapeStyle(LinearGradient(colors: [.red, .orange], startPoint: .topLeading, endPoint: .bottomTrailing))
                    )
            }
            .disabled(vm.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !vm.isStreaming)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.regularMaterial)
    }

    private func sendMessage() {
        guard !vm.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        inputFocused = false
        Task { await vm.send() }
    }
}
