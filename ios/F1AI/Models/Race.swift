import Foundation

struct LapRecord: Codable, Hashable {
    let time: String
    let driver: String
    let year: Int
}

struct CircuitInfo: Codable, Hashable {
    let circuitName: String
    let trackLengthKm: Double
    let laps: Int
    let lapRecord: LapRecord
    let firstGp: Int
    let circuitType: String

    enum CodingKeys: String, CodingKey {
        case circuitName = "circuit_name"
        case trackLengthKm = "track_length_km"
        case laps
        case lapRecord = "lap_record"
        case firstGp = "first_gp"
        case circuitType = "circuit_type"
    }
}

struct RaceEvent: Codable, Identifiable, Hashable {
    let round: Int
    let name: String
    let location: String
    let date: String?
    let sessions: [String: String]
    let status: String
    let circuit: CircuitInfo?
    let isSprint: Bool?

    var id: Int { round }

    var raceStatus: RaceStatus {
        switch status {
        case "completed": return .completed
        case "in_progress": return .inProgress
        default: return .upcoming
        }
    }

    enum CodingKeys: String, CodingKey {
        case round, name, location, date, sessions, status, circuit
        case isSprint = "is_sprint"
    }
}

enum RaceStatus: String {
    case completed, inProgress, upcoming

    var label: String {
        switch self {
        case .completed: return "Completed"
        case .inProgress: return "Live"
        case .upcoming: return "Upcoming"
        }
    }
}
