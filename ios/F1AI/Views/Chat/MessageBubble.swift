import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 48) }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                if message.role == .assistant {
                    HStack(spacing: 4) {
                        Image(systemName: "headphones")
                            .font(.system(size: 10))
                        Text("RACE ENGINEER")
                            .font(.system(size: 9, weight: .bold))
                            .tracking(1)
                    }
                    .foregroundStyle(.secondary)
                }

                if message.role == .assistant {
                    assistantContent
                        .padding(12)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
                } else {
                    Text(markdownContent)
                        .font(.system(size: 14))
                        .textSelection(.enabled)
                        .padding(12)
                        .background(
                            LinearGradient(
                                colors: [.red, .orange],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            in: RoundedRectangle(cornerRadius: 16)
                        )
                        .foregroundStyle(.white)
                }
            }

            if message.role == .assistant { Spacer(minLength: 48) }
        }
    }

    // MARK: - Assistant content with table support

    private var assistantContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            let blocks = parseBlocks(message.content)
            ForEach(blocks.indices, id: \.self) { i in
                switch blocks[i] {
                case .text(let str):
                    if !str.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(markdownString(str))
                            .font(.system(size: 14))
                            .textSelection(.enabled)
                    }
                case .table(let headers, let rows):
                    tableView(headers: headers, rows: rows)
                }
            }
        }
    }

    // MARK: - Table rendering

    private func tableView(headers: [String], rows: [[String]]) -> some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                ForEach(headers.indices, id: \.self) { i in
                    Text(headers[i])
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: columnAlignment(index: i, count: headers.count))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 4)
                }
            }

            Divider().background(Color.secondary.opacity(0.3))

            // Data rows
            ForEach(rows.indices, id: \.self) { rowIdx in
                let row = rows[rowIdx]
                HStack(spacing: 0) {
                    ForEach(row.indices, id: \.self) { colIdx in
                        Text(row[colIdx])
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(rowIdx == 0 ? Color.primary : Color.primary.opacity(0.85))
                            .frame(maxWidth: .infinity, alignment: columnAlignment(index: colIdx, count: row.count))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                    }
                }
                .background {
                    if rowIdx % 2 == 0 {
                        Color.white.opacity(0.03)
                    }
                }
            }
        }
        .background(.black.opacity(0.2), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.15)))
    }

    private func columnAlignment(index: Int, count: Int) -> Alignment {
        if index == 0 { return .leading }
        if index == count - 1 { return .trailing }
        return .center
    }

    // MARK: - Markdown

    private var markdownContent: AttributedString {
        markdownString(message.content)
    }

    private func markdownString(_ str: String) -> AttributedString {
        (try? AttributedString(markdown: str, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(str)
    }

    // MARK: - Block parsing (text vs table)

    private enum ContentBlock {
        case text(String)
        case table(headers: [String], rows: [[String]])
    }

    private func parseBlocks(_ content: String) -> [ContentBlock] {
        let lines = content.components(separatedBy: "\n")
        var blocks: [ContentBlock] = []
        var textBuffer: [String] = []
        var tableLines: [String] = []
        var inTable = false

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            let isTableLine = trimmed.hasPrefix("|") && trimmed.hasSuffix("|") && trimmed.count > 2

            if isTableLine {
                if !inTable {
                    // Flush text buffer
                    if !textBuffer.isEmpty {
                        blocks.append(.text(textBuffer.joined(separator: "\n")))
                        textBuffer = []
                    }
                    inTable = true
                }
                tableLines.append(trimmed)
            } else {
                if inTable {
                    // Flush table
                    if let table = parseTable(tableLines) {
                        blocks.append(table)
                    }
                    tableLines = []
                    inTable = false
                }
                textBuffer.append(line)
            }
        }

        // Flush remaining
        if inTable, let table = parseTable(tableLines) {
            blocks.append(table)
        }
        if !textBuffer.isEmpty {
            blocks.append(.text(textBuffer.joined(separator: "\n")))
        }

        return blocks
    }

    private func parseTable(_ lines: [String]) -> ContentBlock? {
        guard lines.count >= 2 else { return nil }

        func splitRow(_ line: String) -> [String] {
            line.split(separator: "|", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
        }

        let headers = splitRow(lines[0])
        guard !headers.isEmpty else { return nil }

        var rows: [[String]] = []
        for i in 1..<lines.count {
            let trimmed = lines[i].trimmingCharacters(in: .whitespaces)
            // Skip separator rows (|---|---|)
            if trimmed.contains(where: { $0 != "|" && $0 != "-" && $0 != ":" && $0 != " " }) {
                let cells = splitRow(lines[i])
                // Pad or trim to match header count
                let padded = (0..<headers.count).map { idx in
                    idx < cells.count ? cells[idx] : ""
                }
                rows.append(padded)
            }
        }

        guard !rows.isEmpty else { return nil }
        return .table(headers: headers, rows: rows)
    }
}
