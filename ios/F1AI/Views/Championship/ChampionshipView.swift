import SwiftUI

struct ChampionshipView: View {
    @State private var vm = ChampionshipViewModel()
    @State private var championship = 0  // 0=WDC, 1=WCC
    let year: Int

    // Preset labels for what-if buttons
    private var presets: [(label: String, races: Int)] {
        let remaining = vm.upcomingRaces.count
        guard remaining > 0 else { return [] }
        var options: [(String, Int)] = []
        if remaining >= 3 { options.append(("Next 3", 3)) }
        if remaining >= 5 { options.append(("Next 5", 5)) }
        options.append(("All \(remaining)", remaining))
        return options
    }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView("Loading championship...").padding(.top, 60)
            } else if let error = vm.error {
                ContentUnavailableView {
                    Label("Something went wrong", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Retry") { Task { await vm.load(year: year) } }
                        .buttonStyle(.borderedProminent).tint(.red)
                }
            } else {
                VStack(spacing: 16) {
                    // WDC / WCC toggle
                    Picker("Championship", selection: $championship) {
                        Text("Drivers").tag(0)
                        Text("Constructors").tag(1)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)

                    if championship == 0 {
                        wdcSection
                    } else {
                        wccSection
                    }
                }
            }
        }
        .task {
            if vm.drivers.isEmpty {
                await vm.load(year: year)
            }
        }
    }

    // MARK: - WDC

    @ViewBuilder
    private var wdcSection: some View {
        if vm.wdcClinched, let champion = vm.wdcChampion {
            clinchBanner(name: champion.driver, team: champion.team, points: champion.points, isDriver: true)
        } else if vm.wdcContenders.isEmpty {
            ContentUnavailableView("No Contenders", systemImage: "trophy")
        } else {
            LazyVStack(spacing: 8) {
                whatIfControls

                Text("\(vm.wdcContenders.count) drivers still mathematically in contention")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)

                ForEach(vm.wdcContenders) { driver in
                    ChampionshipDriverRow(
                        standing: driver,
                        pointsNeeded: vm.pointsToOvertake(driver: driver),
                        maxRemaining: vm.maxPointsRemaining,
                        isLeader: driver.position == 1
                    )
                    .padding(.horizontal)
                }
            }
        }
    }

    // MARK: - WCC

    @ViewBuilder
    private var wccSection: some View {
        if vm.wccClinched, let champion = vm.wccChampion {
            clinchBanner(name: champion.team, team: "", points: champion.points, isDriver: false)
        } else if vm.wccContenders.isEmpty {
            ContentUnavailableView("No Contenders", systemImage: "trophy")
        } else {
            LazyVStack(spacing: 8) {
                whatIfControls

                Text("\(vm.wccContenders.count) teams still mathematically in contention")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)

                ForEach(vm.wccContenders) { team in
                    ChampionshipConstructorRow(
                        standing: team,
                        pointsNeeded: vm.wccPointsToOvertake(team: team),
                        isLeader: team.position == 1
                    )
                    .padding(.horizontal)
                }
            }
        }
    }

    // MARK: - What-if controls (preset buttons + stepper)

    @ViewBuilder
    private var whatIfControls: some View {
        if !vm.upcomingRaces.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("If the challenger wins...")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)

                // Preset buttons
                HStack(spacing: 8) {
                    ForEach(presets, id: \.label) { preset in
                        Button {
                            vm.whatIfRaces = preset.races
                        } label: {
                            Text(preset.label)
                                .font(.system(size: 12, weight: .bold))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 7)
                                .background(
                                    vm.whatIfRaces == preset.races
                                        ? Color.red.opacity(0.8)
                                        : Color.white.opacity(0.08),
                                    in: Capsule()
                                )
                                .foregroundStyle(.white)
                        }
                    }
                    Spacer()

                    // Fine-grained Stepper
                    Stepper("", value: $vm.whatIfRaces,
                            in: 1...max(1, vm.upcomingRaces.count))
                        .labelsHidden()
                        .scaleEffect(0.85)
                }
                .padding(.horizontal)
            }
        }
    }

    // MARK: - Clinch banner

    func clinchBanner(name: String, team: String, points: Double, isDriver: Bool) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "trophy.fill")
                .font(.system(size: 40))
                .foregroundStyle(.yellow)
            Text("\(name) is the \(currentYear) \(isDriver ? "World Driver" : "Constructors'") Champion")
                .font(.system(size: 17, weight: .bold))
                .multilineTextAlignment(.center)
            Text("\(Int(points)) points")
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
        }
        .padding(32)
        .frame(maxWidth: .infinity)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private var currentYear: String { String(year) }
}
