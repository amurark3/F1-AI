import SwiftUI

struct LiveTab: View {
    @State private var vm = LiveTimingViewModel()
    @State private var calendarVM = CalendarViewModel()

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
                if calendarVM.schedule.isEmpty {
                    await calendarVM.loadSchedule()
                }
            }
        }
    }

    private func liveContent(race: RaceEvent) -> some View {
        VStack(spacing: 0) {
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

            // Timing tower
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
        }
        .onAppear {
            vm.connect(year: calendarVM.selectedYear, round: race.round)
        }
        .onDisappear {
            vm.disconnect()
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
