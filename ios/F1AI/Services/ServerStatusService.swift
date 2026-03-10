import Foundation

enum ServerStatus: Equatable {
    case unknown
    case warming
    case ready
}

@Observable
final class ServerStatusService {
    static let shared = ServerStatusService()

    var status: ServerStatus = .unknown

    private var pollTask: Task<Void, Never>?
    private let probeSession: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 3
        config.timeoutIntervalForResource = 10
        self.probeSession = URLSession(configuration: config)
    }

    func startPolling() {
        guard status != .ready else { return }
        status = .warming

        pollTask = Task {
            while !Task.isCancelled {
                let isHealthy = await probeHealth()
                if isHealthy {
                    status = .ready
                    return
                }
                try? await Task.sleep(for: .seconds(4))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
        status = .unknown
    }

    private func probeHealth() async -> Bool {
        let baseURL = APIClient.shared.baseURL
        guard let url = URL(string: "\(baseURL)/api/health") else { return false }
        do {
            let (_, response) = try await probeSession.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
