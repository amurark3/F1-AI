import Foundation

@Observable
final class APIClient {
    static let shared = APIClient()

    var baseURL: String = "https://f1-ai.onrender.com"

    private let session: URLSession
    private let decoder: JSONDecoder
    private let cache = CacheService.shared

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 35
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
        self.decoder = JSONDecoder()
    }

    // MARK: - Generic cached fetch

    private func fetchCached<T: Codable>(
        url: URL,
        cacheKey: String,
        maxAge: TimeInterval = 3600
    ) async throws -> T {
        // Try cache first
        if let cached = await cache.get(key: cacheKey, maxAge: maxAge) {
            if let decoded = try? decoder.decode(T.self, from: cached) {
                return decoded
            }
        }

        // Fetch from network
        let (data, _) = try await session.data(from: url)
        let decoded = try decoder.decode(T.self, from: data)

        // Save to cache
        await cache.set(key: cacheKey, data: data)

        return decoded
    }

    // MARK: - Schedule

    func fetchSchedule(year: Int) async throws -> [RaceEvent] {
        let url = URL(string: "\(baseURL)/api/schedule/\(year)")!
        return try await fetchCached(url: url, cacheKey: "schedule-\(year)", maxAge: 1800)
    }

    // MARK: - Race Detail

    func fetchRaceDetail(year: Int, round: Int) async throws -> RaceDetailResponse {
        let url = URL(string: "\(baseURL)/api/race/\(year)/\(round)")!
        // Race details for completed races can be cached longer
        return try await fetchCached(url: url, cacheKey: "race-\(year)-\(round)", maxAge: 86400)
    }

    // MARK: - Standings

    func fetchDriverStandings(year: Int) async throws -> [DriverStanding] {
        let url = URL(string: "\(baseURL)/api/standings/drivers/\(year)")!
        return try await fetchCached(url: url, cacheKey: "drivers-\(year)", maxAge: 3600)
    }

    func fetchConstructorStandings(year: Int) async throws -> [ConstructorStanding] {
        let url = URL(string: "\(baseURL)/api/standings/constructors/\(year)")!
        return try await fetchCached(url: url, cacheKey: "constructors-\(year)", maxAge: 3600)
    }

    // MARK: - Compare

    func fetchComparison(year: Int, driver1: String, driver2: String) async throws -> CompareResponse {
        let d1 = driver1.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? driver1
        let d2 = driver2.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? driver2
        let url = URL(string: "\(baseURL)/api/compare/\(year)/\(d1)/\(d2)")!
        return try await fetchCached(url: url, cacheKey: "compare-\(year)-\(d1)-\(d2)", maxAge: 3600)
    }

    // MARK: - Health

    func healthCheck() async -> Bool {
        guard let url = URL(string: "\(baseURL)/api/health") else { return false }
        do {
            let (_, response) = try await session.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
