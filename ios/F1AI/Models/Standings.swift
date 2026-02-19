import Foundation

struct DriverStanding: Codable, Identifiable, Hashable {
    let position: Int
    let driver: String
    let team: String
    let points: Double
    let wins: Int

    var id: Int { position }
}

struct ConstructorStanding: Codable, Identifiable, Hashable {
    let position: Int
    let team: String
    let points: Double
    let wins: Int

    var id: Int { position }
}
