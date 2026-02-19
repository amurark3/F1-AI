import Foundation

@Observable
final class LiveTimingService {
    var isConnected = false
    var positions: [LivePosition] = []
    var sessionStatus: SessionStatus?
    var lastFlag: FlagEvent?

    private var webSocketTask: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)

    func connect(baseURL: String, year: Int, round: Int) {
        let wsURL = baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")

        guard let url = URL(string: "\(wsURL)/api/live/\(year)/\(round)") else { return }

        disconnect()

        let task = session.webSocketTask(with: url)
        self.webSocketTask = task
        task.resume()
        isConnected = true

        receiveMessages()
    }

    func disconnect() {
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
                self.receiveMessages() // Continue listening
            case .failure:
                Task { @MainActor in
                    self.isConnected = false
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
