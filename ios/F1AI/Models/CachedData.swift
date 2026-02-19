import Foundation
import SwiftData

/// Cached API response stored in SwiftData for offline access.
@Model
final class CachedResponse {
    @Attribute(.unique) var key: String
    var data: Data
    var timestamp: Date

    init(key: String, data: Data) {
        self.key = key
        self.data = data
        self.timestamp = .now
    }

    /// Check if cache entry is still fresh (within given seconds).
    func isFresh(maxAge: TimeInterval = 3600) -> Bool {
        Date.now.timeIntervalSince(timestamp) < maxAge
    }
}
