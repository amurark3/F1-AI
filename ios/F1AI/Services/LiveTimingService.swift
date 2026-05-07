import Foundation

@Observable
final class LiveTimingService {
    var isConnected = false
    var positions: [LivePosition] = []
    var sessionStatus: SessionStatus?
    var lastFlag: FlagEvent?
    var commentaryEntries: [CommentaryEntry] = []

    private var webSocketTask: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)
    private var reconnectBaseURL: String?
    private var reconnectYear: Int?
    private var reconnectRound: Int?

    func connect(baseURL: String, year: Int, round: Int) {
        let wsURL = baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")

        guard let url = URL(string: "\(wsURL)/api/live/\(year)/\(round)") else { return }

        // Cancel old task without touching reconnect params
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil

        // Store for auto-reconnect (set AFTER cancel, not before)
        reconnectBaseURL = baseURL
        reconnectYear = year
        reconnectRound = round

        let task = session.webSocketTask(with: url)
        self.webSocketTask = task
        task.resume()
        isConnected = true

        receiveMessages()
    }

    /// Manual disconnect — clears reconnect params so auto-reconnect stops.
    func disconnect() {
        reconnectBaseURL = nil
        reconnectYear = nil
        reconnectRound = nil
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        isConnected = false
    }

    private func receiveMessages() {
        webSocketTask?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                self.handleMessage(message)
                self.receiveMessages()
            case .failure:
                Task { @MainActor in
                    self.isConnected = false
                    guard let base = self.reconnectBaseURL,
                          let year = self.reconnectYear,
                          let round = self.reconnectRound else { return }
                    try? await Task.sleep(for: .seconds(5))
                    self.connect(baseURL: base, year: year, round: round)
                }
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        let data: Data
        switch message {
        case .string(let text):
            data = Data(text.utf8)
        case .data(let d):
            data = d
        @unknown default:
            return
        }

        guard let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = raw["type"] as? String else { return }

        if type == "commentary" {
            guard let dataObj = raw["data"],
                  let dataData = try? JSONSerialization.data(withJSONObject: dataObj),
                  let entry = try? JSONDecoder().decode(CommentaryEntry.self, from: dataData)
            else { return }
            Task { @MainActor in
                self.commentaryEntries = ([entry] + self.commentaryEntries).prefix(100).map { $0 }
            }
            return
        }

        guard let decoded = try? JSONDecoder().decode(LiveTimingMessage.self, from: data) else { return }

        Task { @MainActor in
            switch decoded.data {
            case .positions(let pos):
                self.positions = pos
            case .sessionStatus(let status):
                self.sessionStatus = status
            case .flag(let flag):
                self.lastFlag = flag
            }
        }
    }
}
