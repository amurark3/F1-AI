import SwiftUI

struct RaceResultsTable: View {
    let results: [RaceResult]
    @State private var expanded = false

    private var visible: [RaceResult] {
        expanded ? results : Array(results.prefix(10))
    }

    var body: some View {
        VStack(spacing: 2) {
            // Header
            HStack(spacing: 0) {
                Text("POS").frame(width: 32, alignment: .leading)
                Text("DRIVER").frame(maxWidth: .infinity, alignment: .leading)
                Text("GRID").frame(width: 36)
                Text("+/-").frame(width: 36)
                Text("TIME").frame(width: 80, alignment: .trailing)
                Text("PTS").frame(width: 32, alignment: .trailing)
            }
            .font(.system(size: 10, weight: .bold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)
            .padding(.bottom, 4)

            ForEach(visible) { result in
                raceRow(result)
            }

            if results.count > 10 {
                Button {
                    withAnimation(.spring(duration: 0.3)) { expanded.toggle() }
                } label: {
                    HStack(spacing: 4) {
                        Text(expanded ? "Show less" : "Full classification")
                        Image(systemName: expanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10))
                    }
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
                }
            }
        }
    }

    @ViewBuilder
    private func raceRow(_ r: RaceResult) -> some View {
        let change = r.gridChange
        let changeStr: String = {
            guard let c = change else { return "-" }
            if c > 0 { return "+\(c)" }
            if c < 0 { return "\(c)" }
            return "0"
        }()

        HStack(spacing: 0) {
            Text(r.position.map(String.init) ?? "-")
                .font(.system(size: 12, weight: .black))
                .foregroundStyle(r.isTop3 ? Color.primary : Color.secondary)
                .frame(width: 32, alignment: .leading)

            Text(r.fullName)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(r.isTop3 ? Color.primary : Color.primary.opacity(0.8))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(r.grid.map(String.init) ?? "PL")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 36)

            Text(changeStr)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(changeColor(changeStr))
                .frame(width: 36)

            Text(r.time.isEmpty ? "-" : r.time)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(r.isDNF ? Color.red : Color.secondary)
                .lineLimit(1)
                .frame(width: 80, alignment: .trailing)

            Text(r.points > 0 ? String(format: "%.0f", r.points) : "")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(r.points > 0 ? Color.primary : Color.secondary)
                .frame(width: 32, alignment: .trailing)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background {
            if r.isTop3 {
                RoundedRectangle(cornerRadius: 8).fill(.ultraThinMaterial)
            }
        }
        .opacity(r.isDNF ? 0.5 : 1)
    }

    private func changeColor(_ str: String) -> Color {
        if str.hasPrefix("+") { return .green }
        if str.hasPrefix("-") { return .red }
        return .secondary
    }
}

struct QualifyingTable: View {
    let qualifying: [String: [QualifyingEntry]]
    @State private var activeTab = "Q3"

    private let tabs = ["Q3", "Q2", "Q1"]

    private var availableTabs: [String] {
        tabs.filter { qualifying[$0]?.isEmpty == false }
    }

    private var currentTab: String {
        qualifying[activeTab] != nil ? activeTab : availableTabs.first ?? "Q3"
    }

    private var entries: [QualifyingEntry] {
        qualifying[currentTab] ?? []
    }

    var body: some View {
        VStack(spacing: 12) {
            // Q tabs
            HStack(spacing: 4) {
                ForEach(tabs, id: \.self) { tab in
                    let available = qualifying[tab]?.isEmpty == false
                    Button {
                        if available { withAnimation { activeTab = tab } }
                    } label: {
                        Text(tab)
                            .font(.system(size: 12, weight: .bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background {
                                if currentTab == tab {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing))
                                }
                            }
                            .foregroundStyle(tabForeground(tab: tab, isCurrent: currentTab == tab, available: available))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .disabled(!available)
                }
            }
            .padding(4)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))

            // Entries
            VStack(spacing: 2) {
                HStack(spacing: 0) {
                    Text("POS").frame(width: 32, alignment: .leading)
                    Text("DRIVER").frame(maxWidth: .infinity, alignment: .leading)
                    Text("TIME").frame(width: 90, alignment: .trailing)
                }
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 8)

                ForEach(entries) { entry in
                    qualifyingRow(entry)
                }
            }
        }
    }

    @ViewBuilder
    private func qualifyingRow(_ entry: QualifyingEntry) -> some View {
        let isPole = entry.position == 1 && currentTab == "Q3"

        HStack(spacing: 0) {
            Text(String(entry.position))
                .font(.system(size: 12, weight: .black))
                .foregroundStyle(positionColor(position: entry.position, isPole: isPole))
                .frame(width: 32, alignment: .leading)

            Text(entry.fullName)
                .font(.system(size: 12, weight: .medium))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(entry.time)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(isPole ? Color.primary : Color.secondary)
                .frame(width: 90, alignment: .trailing)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background {
            if isPole {
                RoundedRectangle(cornerRadius: 8).fill(.ultraThinMaterial)
            }
        }
    }

    private func positionColor(position: Int, isPole: Bool) -> Color {
        if isPole { return .red }
        if position <= 3 { return .primary }
        return .secondary
    }

    private func tabForeground(tab: String, isCurrent: Bool, available: Bool) -> Color {
        if isCurrent { return .white }
        if available { return .secondary }
        return Color.secondary.opacity(0.3)
    }
}
