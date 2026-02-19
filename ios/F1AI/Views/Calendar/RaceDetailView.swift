import SwiftUI

struct RaceDetailView: View {
    let race: RaceEvent
    let year: Int
    @Binding var mainTab: Int

    @State private var vm = RaceDetailViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header

                SessionSchedule(sessions: race.sessions)

                if let circuit = vm.detail?.circuit ?? race.circuit {
                    CircuitInfoCard(circuit: circuit)
                }

                if race.raceStatus == .upcoming {
                    CountdownView(countdown: countdownText)
                }

                // Show results section for completed and in-progress races
                if race.raceStatus == .completed || race.raceStatus == .inProgress {
                    resultsSection
                }
            }
            .padding()
        }
        .background(Color(.systemBackground))
        .navigationTitle(race.name.replacingOccurrences(of: "Grand Prix", with: "GP"))
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if race.raceStatus == .completed || race.raceStatus == .inProgress {
                await vm.loadDetail(year: year, round: race.round, sessions: race.sessions)
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text("ROUND \(race.round)")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(2)
                    .foregroundStyle(
                        LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing)
                    )

                if race.isSprint == true {
                    Text("SPRINT")
                        .font(.system(size: 9, weight: .bold))
                        .tracking(1)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.yellow.opacity(0.15))
                        .foregroundStyle(.yellow)
                        .clipShape(Capsule())
                }

                Spacer()

                StatusBadge(status: race.raceStatus)
            }

            Text(race.name.uppercased())
                .font(.system(size: 24, weight: .black))
                .italic()

            Text(race.location)
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Results Section

    @ViewBuilder
    private var resultsSection: some View {
        if vm.isLoading {
            ProgressView("Loading race data...")
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
        } else if let error = vm.error {
            VStack(spacing: 8) {
                Text("Failed to load race data.")
                    .foregroundStyle(.secondary)
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                Button("Retry") { vm.retry(year: year, round: race.round) }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 32)
        } else if let detail = vm.detail {
            // Podium (only if race results exist)
            if let podium = detail.podium {
                VStack(spacing: 8) {
                    HStack {
                        Text("PODIUM")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(2)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if let results = detail.raceResults {
                            ShareResultButton(
                                raceName: race.name,
                                year: year,
                                podium: podium,
                                results: results
                            )
                        }
                    }
                    PodiumView(podium: podium)
                }
            }

            resultTabs(detail: detail)
        }
    }

    // MARK: - Result Tabs

    @ViewBuilder
    private func resultTabs(detail: RaceDetailResponse) -> some View {
        VStack(spacing: 12) {
            // Tab bar
            HStack(spacing: 4) {
                ForEach(vm.availableTabs, id: \.self) { tab in
                    let status = vm.tabStatus(for: tab, sessions: race.sessions)
                    let isLocked = status == .locked
                    let isSelected = vm.selectedTab == tab

                    Button {
                        if !isLocked {
                            withAnimation { vm.selectedTab = tab }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            if isLocked {
                                Image(systemName: "lock.fill")
                                    .font(.system(size: 9))
                            } else {
                                Image(systemName: tabIcon(tab))
                                    .font(.system(size: 10))
                            }
                            Text(tab.rawValue)
                                .font(.system(size: 12, weight: .bold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background {
                            if isSelected && !isLocked {
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing))
                            }
                        }
                        .foregroundStyle(tabForeground(isSelected: isSelected, isLocked: isLocked))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .disabled(isLocked)
                }
            }
            .padding(4)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))

            // Content
            tabContent(detail: detail)
        }
    }

    @ViewBuilder
    private func tabContent(detail: RaceDetailResponse) -> some View {
        let status = vm.tabStatus(for: vm.selectedTab, sessions: race.sessions)

        switch status {
        case .locked:
            lockedTabView

        case .empty:
            emptyResultsView

        case .available:
            switch vm.selectedTab {
            case .race:
                if let results = detail.raceResults {
                    RaceResultsTable(results: results)
                }
            case .qualifying:
                if let quali = detail.qualifying {
                    QualifyingTable(qualifying: quali)
                }
            case .sprint:
                if let results = detail.sprintResults {
                    RaceResultsTable(results: results)
                }
            case .sprintQuali:
                if let quali = detail.sprintQualifying {
                    QualifyingTable(qualifying: quali)
                }
            }
        }
    }

    // MARK: - Empty State

    private var emptyResultsView: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 28))
                .foregroundStyle(.secondary)

            Text("No Results Found")
                .font(.system(size: 15, weight: .bold))

            Text("Results for this session are not available yet.")
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .padding(.horizontal, 16)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }

    // MARK: - Locked Tab

    private var lockedTabView: some View {
        VStack(spacing: 16) {
            Image(systemName: "lock.fill")
                .font(.system(size: 28))
                .foregroundStyle(.secondary)

            Text("Session Not Yet Complete")
                .font(.system(size: 15, weight: .bold))

            Text("Results will be updated once the \(vm.selectedTab.rawValue.lowercased()) session is over.")
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            // If race is live, show jump to live button
            if race.raceStatus == .inProgress || vm.isSessionLive(sessions: race.sessions) {
                jumpToLiveCard
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .padding(.horizontal, 16)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }

    // MARK: - Jump to Live

    private var jumpToLiveCard: some View {
        Button {
            withAnimation { mainTab = 1 }
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(.red)
                    .frame(width: 8, height: 8)
                    .overlay {
                        Circle()
                            .fill(.red.opacity(0.4))
                            .frame(width: 16, height: 16)
                    }

                Text("Watch Live")
                    .font(.system(size: 14, weight: .bold))

                Spacer()

                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 14))

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .bold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing),
                in: RoundedRectangle(cornerRadius: 12)
            )
        }
        .padding(.top, 4)
    }

    // MARK: - Helpers

    private func tabIcon(_ tab: RaceDetailViewModel.ResultTab) -> String {
        switch tab {
        case .race: return "trophy.fill"
        case .qualifying: return "timer"
        case .sprint, .sprintQuali: return "bolt.fill"
        }
    }

    private func tabForeground(isSelected: Bool, isLocked: Bool) -> Color {
        if isLocked { return Color.secondary.opacity(0.4) }
        if isSelected { return .white }
        return Color.secondary
    }

    private var countdownText: String {
        guard let raceTime = race.sessions["Race"],
              let date = parseDate(raceTime)
        else { return "--" }

        let diff = date.timeIntervalSince(Date())
        guard diff > 0 else { return "NOW" }

        let days = Int(diff / 86400)
        let hours = Int((diff.truncatingRemainder(dividingBy: 86400)) / 3600)
        let mins = Int((diff.truncatingRemainder(dividingBy: 3600)) / 60)

        if days > 0 { return "\(days)d \(hours)h \(mins)m" }
        return "\(hours)h \(mins)m"
    }

    private func parseDate(_ str: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        return iso.date(from: str) ?? iso.date(from: str + "Z")
    }
}
