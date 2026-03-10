import ActivityKit
import SwiftUI

private enum LiveSegment: String, CaseIterable {
    case timing = "Timing"
    case commentary = "Commentary"
}

struct LiveTab: View {
    @State private var vm = LiveTimingViewModel()
    @State private var calendarVM = CalendarViewModel()
    @State private var liveActivityService = LiveActivityService()
    @State private var selectedSegment: LiveSegment = .timing
    @State private var hasNewCommentary = false
    @State private var serverStatus = ServerStatusService.shared

    var body: some View {
        NavigationStack {
            Group {
                if let liveRace = calendarVM.schedule.first(where: { $0.status == "in_progress" }) {
                    liveContent(race: liveRace)
                } else {
                    noLiveSession
                }
            }
            .navigationTitle("Live")
            .task {
                serverStatus.startPolling()
                if calendarVM.schedule.isEmpty {
                    await calendarVM.loadSchedule()
                }
            }
        }
    }

    private func liveContent(race: RaceEvent) -> some View {
        VStack(spacing: 0) {
            if serverStatus.status == .warming {
                HStack(spacing: 8) {
                    ProgressView()
                        .scaleEffect(0.7)
                    Text("Warming up server...")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
            }

            // Race header
            VStack(spacing: 4) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(race.name.uppercased())
                            .font(.system(size: 16, weight: .black))
                            .italic()
                        Text(race.location)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    HStack(spacing: 6) {
                        Circle()
                            .fill(.red)
                            .frame(width: 6, height: 6)
                        Text("LIVE")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(2)
                            .foregroundStyle(.red)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(.red.opacity(0.1), in: Capsule())
                }
                .padding()
            }
            .background(.regularMaterial)

            Divider()

            // Segment picker
            Picker("", selection: $selectedSegment) {
                ForEach(LiveSegment.allCases, id: \.self) { seg in
                    if seg == .commentary && hasNewCommentary {
                        Label(seg.rawValue, systemImage: "circle.fill")
                            .labelStyle(.titleAndIcon)
                    } else {
                        Text(seg.rawValue)
                    }
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            // Content switch
            switch selectedSegment {
            case .timing:
                ScrollView {
                    if vm.isConnected {
                        if vm.positions.isEmpty {
                            VStack(spacing: 8) {
                                ProgressView()
                                Text("Waiting for timing data...")
                                    .font(.system(size: 13))
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.top, 60)
                        } else {
                            TimingTower(
                                positions: vm.positions,
                                sessionStatus: vm.sessionStatus
                            )
                            .padding(.top, 8)
                        }
                    } else {
                        VStack(spacing: 12) {
                            Image(systemName: "antenna.radiowaves.left.and.right")
                                .font(.system(size: 32))
                                .foregroundStyle(.secondary)
                            Text("Connecting to live timing...")
                                .font(.system(size: 13))
                                .foregroundStyle(.secondary)
                        }
                        .padding(.top, 60)
                    }
                }
            case .commentary:
                CommentaryFeedView(entries: vm.commentaryEntries)
                    .onAppear { hasNewCommentary = false }
            }
        }
        .onChange(of: vm.commentaryEntries.count) {
            if selectedSegment != .commentary {
                hasNewCommentary = true
            }
        }
        .onChange(of: vm.positions) {
            guard !vm.positions.isEmpty else { return }
            if !liveActivityService.isActive {
                liveActivityService.startActivity(
                    race: race,
                    positions: vm.positions,
                    sessionStatus: vm.sessionStatus
                )
            } else {
                Task {
                    await liveActivityService.update(
                        positions: vm.positions,
                        sessionStatus: vm.sessionStatus
                    )
                }
            }
        }
        .onChange(of: vm.sessionStatus?.status) { _, newStatus in
            guard let s = newStatus, s == "finished" || s == "ended" else { return }
            Task {
                await liveActivityService.endActivity(
                    positions: vm.positions,
                    sessionStatus: vm.sessionStatus
                )
            }
        }
        .onAppear {
            let raceYear = race.date.flatMap { Int($0.prefix(4)) } ?? calendarVM.selectedYear
            vm.connect(year: raceYear, round: race.round)
            // Activity starts only after first positions arrive (handled by onChange above)
        }
        .onDisappear {
            vm.disconnect()
            Task {
                await liveActivityService.endActivity(
                    positions: vm.positions,
                    sessionStatus: vm.sessionStatus
                )
            }
        }
        .sensoryFeedback(.impact(weight: .medium), trigger: vm.positions.first?.driver) // Haptic on leader change
    }

    private var noLiveSession: some View {
        VStack(spacing: 16) {
            Image(systemName: "antenna.radiowaves.left.and.right.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No Live Session")
                .font(.system(size: 20, weight: .bold))

            Text("Live timing will appear here during race weekends.")
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            if let nextRace = calendarVM.schedule.first(where: { $0.status == "upcoming" }),
               let countdown = calendarVM.countdown(for: nextRace) {
                VStack(spacing: 4) {
                    Text("NEXT UP")
                        .font(.system(size: 10, weight: .bold))
                        .tracking(2)
                        .foregroundStyle(.secondary)
                    Text(nextRace.name)
                        .font(.system(size: 15, weight: .bold))
                    Text(countdown)
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .foregroundStyle(.orange)
                }
                .padding()
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }
}
