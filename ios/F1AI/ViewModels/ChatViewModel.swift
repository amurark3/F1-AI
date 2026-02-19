import Foundation

@Observable
final class ChatViewModel {
    var messages: [ChatMessage] = []
    var isStreaming = false
    var activeTools: [ToolStatus] = []
    var inputText = ""

    private let streamService = ChatStreamService()

    func send() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isStreaming else { return }

        inputText = ""
        messages.append(ChatMessage(role: .user, content: text))

        isStreaming = true
        activeTools = []

        do {
            let stream = streamService.stream(
                messages: messages,
                baseURL: APIClient.shared.baseURL
            )

            for try await event in stream {
                switch event {
                case .text(let chunk):
                    appendText(chunk)
                case .toolStart(let name):
                    activeTools.append(.active(name: name))
                case .toolEnd(let name):
                    activeTools.removeAll { $0.name == name && $0.isActive }
                    activeTools.append(.completed(name: name))
                }
            }
        } catch {
            // If no assistant message was created yet, create one with the error
            if messages.last?.role != .assistant {
                messages.append(ChatMessage(role: .assistant, content: "Sorry, something went wrong: \(error.localizedDescription)"))
            } else if var last = messages.last, last.content.isEmpty {
                last.content = "Sorry, something went wrong: \(error.localizedDescription)"
                messages[messages.count - 1] = last
            }
        }

        activeTools = []
        isStreaming = false
    }

    /// Append text to the current assistant message, creating it on first chunk
    private func appendText(_ chunk: String) {
        if let last = messages.last, last.role == .assistant {
            var updated = last
            updated.content += chunk
            messages[messages.count - 1] = updated
        } else {
            // First text chunk — create the assistant message now
            messages.append(ChatMessage(role: .assistant, content: chunk))
        }
    }

    func clearHistory() {
        messages = []
    }
}
