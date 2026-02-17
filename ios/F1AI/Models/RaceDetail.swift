import Foundation

struct RaceDetailResponse: Codable {
    let round: Int
    let name: String
    let location: String
    let date: String?
    let sessions: [String: String]
    let circuit: CircuitInfo?
    let raceResults: [RaceResult]?
    let qualifying: [String: [QualifyingEntry]]?
    let podium: [PodiumEntry]?
    let isSprint: Bool?
    let sprintResults: [RaceResult]?
    let sprintQualifying: [String: [QualifyingEntry]]?
    let error: String?
    let timeout: Bool?

    enum CodingKeys: String, CodingKey {
        case round, name, location, date, sessions, circuit, qualifying, podium, error, timeout
        case raceResults = "race_results"
        case isSprint = "is_sprint"
        case sprintResults = "sprint_results"
        case sprintQualifying = "sprint_qualifying"
    }
}

struct RaceResult: Codable, Identifiable, Hashable {
    let position: Int?
    let driver: String
    let fullName: String
    let team: String
    let grid: Int?
    let time: String
    let points: Double
    let status: String

    var id: String { driver }
    var isDNF: Bool { status != "Finished" && !status.contains("Lap") }
    var isTop3: Bool { (position ?? 99) <= 3 }

    var gridChange: Int? {
        guard let pos = position, let g = grid else { return nil }
        return g - pos
    }

    enum CodingKeys: String, CodingKey {
        case position, driver, team, grid, time, points, status
        case fullName = "full_name"
    }
}

struct QualifyingEntry: Codable, Identifiable, Hashable {
    let position: Int
    let driver: String
    let fullName: String
    let team: String
    let time: String

    var id: String { "\(driver)-\(position)" }

    enum CodingKeys: String, CodingKey {
        case position, driver, team, time
        case fullName = "full_name"
    }
}

struct PodiumEntry: Codable, Identifiable, Hashable {
    let position: Int
    let driver: String
    let fullName: String
    let team: String

    var id: Int { position }

    enum CodingKeys: String, CodingKey {
        case position, driver, team
        case fullName = "full_name"
    }
}
