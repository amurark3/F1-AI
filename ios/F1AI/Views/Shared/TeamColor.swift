import SwiftUI

enum TeamColor {
    static let map: [String: Color] = [
        "Red Bull Racing": Color(hex: 0x3671C6),
        "Mercedes": Color(hex: 0x27F4D2),
        "Ferrari": Color(hex: 0xE8002D),
        "McLaren": Color(hex: 0xFF8000),
        "Aston Martin": Color(hex: 0x229971),
        "Alpine": Color(hex: 0xFF87BC),
        "Williams": Color(hex: 0x64C4FF),
        "RB": Color(hex: 0x6692FF),
        "Haas F1 Team": Color(hex: 0xB6BABD),
        "Kick Sauber": Color(hex: 0x52E252),
    ]

    static func color(for team: String) -> Color {
        for (key, color) in map {
            if team.contains(key) { return color }
        }
        return .gray
    }
}

extension Color {
    init(hex: UInt, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}
