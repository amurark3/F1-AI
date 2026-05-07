import Foundation

struct PredictionsResponse: Codable {
    let year: Int
    let round: Int
    let grandPrix: String
    let generatedAt: String
    let dataSources: [String]
    let accuracy: AccuracyStats?
    let predictions: [DriverPrediction]
    let weatherImpact: String?
    let warnings: [String]?
    let error: String?   // backend may return HTTP 200 with an error body — must decode this field

    enum CodingKeys: String, CodingKey {
        case year, round, predictions, accuracy, warnings, error
        case grandPrix = "grand_prix"
        case generatedAt = "generated_at"
        case dataSources = "data_sources"
        case weatherImpact = "weather_impact"
    }
}

struct DriverPrediction: Codable, Identifiable {
    let position: Int
    let driverCode: String
    let driverName: String
    let team: String
    let confidenceLow: Int
    let confidenceHigh: Int
    let factors: [String]

    var id: String { driverCode }

    // Derived: "72–85%" — this is the "win probability" shown on the card
    var confidenceRange: String { "\(confidenceLow)–\(confidenceHigh)%" }

    enum CodingKeys: String, CodingKey {
        case position, team, factors
        case driverCode = "driver_code"
        case driverName = "driver_name"
        case confidenceLow = "confidence_low"
        case confidenceHigh = "confidence_high"
    }
}

struct AccuracyStats: Codable {
    let recentTop3Pct: Int?
    let recentTop10Pct: Int?
    let avgPositionError: Double?
    let racesEvaluated: Int

    enum CodingKeys: String, CodingKey {
        case racesEvaluated = "races_evaluated"
        case recentTop3Pct = "recent_top3_pct"
        case recentTop10Pct = "recent_top10_pct"
        case avgPositionError = "avg_position_error"
    }
}
