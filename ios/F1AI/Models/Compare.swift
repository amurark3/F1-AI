import Foundation

struct CompareResponse: Codable {
    let driver1: CompareDriver
    let driver2: CompareDriver
    let qualifyingH2h: H2HRecord
    let raceH2h: H2HRecord
    let avgRacePosition: AvgPosition
    let rounds: [CompareRound]
    let error: String?

    enum CodingKeys: String, CodingKey {
        case driver1, driver2, rounds, error
        case qualifyingH2h = "qualifying_h2h"
        case raceH2h = "race_h2h"
        case avgRacePosition = "avg_race_position"
    }
}

struct CompareDriver: Codable {
    let code: String
    let name: String
    let team: String
    let points: Double
    let wins: Int
    let position: Int
}

struct H2HRecord: Codable {
    let d1: Int
    let d2: Int
}

struct AvgPosition: Codable {
    let d1: Double?
    let d2: Double?
}

struct CompareRound: Codable, Identifiable {
    let round: Int
    let name: String
    let d1Race: Int?
    let d2Race: Int?
    let d1Quali: Int?
    let d2Quali: Int?

    var id: Int { round }

    enum CodingKeys: String, CodingKey {
        case round, name
        case d1Race = "d1_race"
        case d2Race = "d2_race"
        case d1Quali = "d1_quali"
        case d2Quali = "d2_quali"
    }
}
