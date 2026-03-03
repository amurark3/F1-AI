import SwiftUI

struct PredictionsView: View {
    // Upcoming race passed in from StandingsTab (which already has schedule context)
    // nil = no upcoming race this season
    let upcomingRace: RaceEvent?
    let year: Int

    @State private var vm = PredictionsViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView("Loading predictions...")
                    .padding(.top, 60)
            } else if let error = vm.error {
                // First load failure — ContentUnavailableView with Retry (locked decision)
                ContentUnavailableView {
                    Label("Something went wrong", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Retry") {
                        guard let race = upcomingRace else { return }
                        vm.selectedYear = year
                        vm.selectedRound = race.round
                        Task { await vm.loadPredictions(year: year, round: race.round) }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                }
            } else if vm.hasNoUpcomingRace || upcomingRace == nil {
                // Empty state — no upcoming race (locked decision: show friendly message, not hidden view)
                ContentUnavailableView {
                    Label("No Upcoming Race", systemImage: "flag.checkered")
                } description: {
                    Text("Race predictions will be available closer to the next round.")
                }
            } else {
                // Content: stacked driver cards
                LazyVStack(spacing: 8) {
                    // Header: accuracy stats if available
                    if let accuracy = vm.response?.accuracy, accuracy.racesEvaluated > 0 {
                        HStack {
                            Text("Based on \(accuracy.racesEvaluated) recent race\(accuracy.racesEvaluated == 1 ? "" : "s")")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(.secondary)
                            Spacer()
                            if let top3 = accuracy.recentTop3Pct {
                                Text("Top 3 accuracy: \(top3)%")
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 4)
                    }

                    ForEach(vm.predictions) { prediction in
                        PredictionDriverCard(prediction: prediction)
                            .padding(.horizontal)
                    }
                }
                .padding(.bottom, 16)
            }
        }
        .task {
            if let race = upcomingRace, vm.predictions.isEmpty {
                vm.selectedYear = year
                vm.selectedRound = race.round
                await vm.loadPredictions(year: year, round: race.round)
            }
        }
        // Toast overlay applied by Plan 05 after ToastView is created
    }
}
