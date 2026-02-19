import Foundation

struct LiveTimingMessage: Codable {
    let type: String
    let data: LiveTimingData
}

enum LiveTimingData: Codable {
    case positions([LivePosition])
    case sessionStatus(SessionStatus)
    case flag(FlagEvent)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let positions = try? container.decode([LivePosition].self) {
            self = .positions(positions)
        } else if let status = try? container.decode(SessionStatus.self) {
            self = .sessionStatus(status)
        } else if let flag = try? container.decode(FlagEvent.self) {
            self = .flag(flag)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown data type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .positions(let p): try container.encode(p)
        case .sessionStatus(let s): try container.encode(s)
        case .flag(let f): try container.encode(f)
        }
    }
}

struct LivePosition: Codable, Identifiable, Hashable {
    let position: Int
    let driver: String
    let gap: String
    let lastLap: String?
    let sector1: Double?
    let sector2: Double?
    let sector3: Double?
    let tyre: String?
    let pitStops: Int?

    var id: String { driver }

    enum CodingKeys: String, CodingKey {
        case position, driver, gap, tyre
        case lastLap = "last_lap"
        case sector1, sector2, sector3
        case pitStops = "pit_stops"
    }
}

struct SessionStatus: Codable, Hashable {
    let status: String
    let lap: Int?
    let totalLaps: Int?

    enum CodingKeys: String, CodingKey {
        case status, lap
        case totalLaps = "total_laps"
    }
}

struct FlagEvent: Codable, Hashable {
    let flag: String
    let sector: Int?
}
