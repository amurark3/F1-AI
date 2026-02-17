import Foundation

struct ChatMessage: Identifiable, Hashable {
    let id: UUID
    let role: ChatRole
    var content: String
    let timestamp: Date

    init(role: ChatRole, content: String) {
        self.id = UUID()
        self.role = role
        self.content = content
        self.timestamp = Date()
    }
}

enum ChatRole: String, Codable, Hashable {
    case user
    case assistant
}

struct ChatRequest: Codable {
    let messages: [ChatRequestMessage]
}

struct ChatRequestMessage: Codable {
    let role: String
    let content: String
}

enum ToolStatus: Identifiable, Hashable {
    case active(name: String)
    case completed(name: String)

    var id: String {
        switch self {
        case .active(let name): return "active-\(name)"
        case .completed(let name): return "done-\(name)"
        }
    }

    var name: String {
        switch self {
        case .active(let name), .completed(let name): return name
        }
    }

    var isActive: Bool {
        if case .active = self { return true }
        return false
    }
}
