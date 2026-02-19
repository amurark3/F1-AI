import Foundation

final class ChatStreamService {
    private let session: URLSession

    private static let allTags = ["[TOOL_START]", "[/TOOL_START]", "[TOOL_END]", "[/TOOL_END]"]

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        self.session = URLSession(configuration: config)
    }

    func stream(
        messages: [ChatMessage],
        baseURL: String
    ) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    let url = URL(string: "\(baseURL)/api/chat")!
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

                    let body = ChatRequest(
                        messages: messages.map {
                            ChatRequestMessage(role: $0.role.rawValue, content: $0.content)
                        }
                    )
                    request.httpBody = try JSONEncoder().encode(body)

                    let (bytes, response) = try await session.bytes(for: request)

                    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                        continuation.finish(throwing: APIError.badResponse)
                        return
                    }

                    var buffer = ""

                    for try await byte in bytes {
                        buffer.append(Character(UnicodeScalar(byte)))

                        // Try extracting complete markers
                        while let result = Self.extractMarker(from: &buffer) {
                            switch result {
                            case .text(let t) where !t.isEmpty:
                                continuation.yield(.text(t))
                            case .toolStart(let name):
                                continuation.yield(.toolStart(name))
                            case .toolEnd(let name):
                                continuation.yield(.toolEnd(name))
                            default:
                                break
                            }
                        }

                        // Flush safe text that can't be part of a marker
                        let flushable = Self.flushableText(from: &buffer)
                        if !flushable.isEmpty {
                            continuation.yield(.text(flushable))
                        }
                    }

                    // Flush anything remaining
                    if !buffer.isEmpty {
                        continuation.yield(.text(buffer))
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Extract a complete marker pair from the buffer.
    private static func extractMarker(from buffer: inout String) -> StreamEvent? {
        let pattern = #"\[(TOOL_START|TOOL_END)\](.+?)\[/(TOOL_START|TOOL_END)\]"#

        guard let match = buffer.range(of: pattern, options: .regularExpression) else {
            return nil
        }

        // If there's text before the marker, return that first
        let before = String(buffer[buffer.startIndex..<match.lowerBound])
        let markerText = String(buffer[match])
        buffer = String(buffer[match.upperBound...])

        if !before.isEmpty {
            buffer = markerText + buffer
            return .text(before)
        }

        if markerText.hasPrefix("[TOOL_START]") {
            let name = markerText
                .replacingOccurrences(of: "[TOOL_START]", with: "")
                .replacingOccurrences(of: "[/TOOL_START]", with: "")
            return .toolStart(name)
        } else {
            let name = markerText
                .replacingOccurrences(of: "[TOOL_END]", with: "")
                .replacingOccurrences(of: "[/TOOL_END]", with: "")
            return .toolEnd(name)
        }
    }

    /// Flush text from the buffer that definitely can't be part of a marker.
    /// Scans for the first `[` that could start a tag and holds from there.
    private static func flushableText(from buffer: inout String) -> String {
        guard !buffer.isEmpty else { return "" }

        var idx = buffer.startIndex
        while idx < buffer.endIndex {
            if buffer[idx] == "[" {
                let suffix = String(buffer[idx...])
                if couldBePartOfMarker(suffix) {
                    let safe = String(buffer[buffer.startIndex..<idx])
                    buffer = suffix
                    return safe
                }
            }
            idx = buffer.index(after: idx)
        }

        // No potential marker brackets — flush everything
        let text = buffer
        buffer = ""
        return text
    }

    /// Check if text starting with `[` could be or contain a marker tag.
    private static func couldBePartOfMarker(_ text: String) -> Bool {
        // Text is a partial tag (e.g. "[", "[TO", "[TOOL_START")
        if allTags.contains(where: { $0.hasPrefix(text) }) { return true }
        // Text starts with a complete tag — we're past the opener accumulating content
        // (e.g. "[TOOL_START]Get Season Schedule" or "[TOOL_START]Get Schedule[/TOO")
        if allTags.contains(where: { text.hasPrefix($0) }) { return true }
        return false
    }
}

enum StreamEvent {
    case text(String)
    case toolStart(String)
    case toolEnd(String)
}

enum APIError: LocalizedError {
    case badResponse
    case timeout

    var errorDescription: String? {
        switch self {
        case .badResponse: return "Server returned an unexpected response."
        case .timeout: return "Request timed out. Try again."
        }
    }
}
