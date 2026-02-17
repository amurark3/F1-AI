import Foundation
import SwiftData

/// Simple cache layer using SwiftData for offline access.
actor CacheService {
    static let shared = CacheService()

    private var container: ModelContainer?

    private init() {
        do {
            container = try ModelContainer(for: CachedResponse.self)
        } catch {
            print("SwiftData init error: \(error)")
        }
    }

    /// Get cached data for a key, if fresh enough.
    func get(key: String, maxAge: TimeInterval = 3600) -> Data? {
        guard let container else { return nil }
        let context = ModelContext(container)

        let predicate = #Predicate<CachedResponse> { $0.key == key }
        var descriptor = FetchDescriptor(predicate: predicate)
        descriptor.fetchLimit = 1

        guard let entry = try? context.fetch(descriptor).first else { return nil }
        return entry.isFresh(maxAge: maxAge) ? entry.data : nil
    }

    /// Store data in cache.
    func set(key: String, data: Data) {
        guard let container else { return }
        let context = ModelContext(container)

        // Delete existing entry for this key
        let predicate = #Predicate<CachedResponse> { $0.key == key }
        let descriptor = FetchDescriptor(predicate: predicate)
        if let existing = try? context.fetch(descriptor) {
            for item in existing {
                context.delete(item)
            }
        }

        context.insert(CachedResponse(key: key, data: data))
        try? context.save()
    }
}
