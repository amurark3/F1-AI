import SwiftUI

struct StandingsTab: View {
    @State private var vm = StandingsViewModel()
    @State private var calVm = CalendarViewModel()
    @State private var segment = 0   // 0=Drivers, 1=Constructors, 2=Predictions, 3=Championship

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Fallback notice
                    if vm.isUsingFallback {
                        HStack(spacing: 6) {
                            Image(systemName: "info.circle")
                            Text("\(vm.selectedYear) standings not yet available — showing \(vm.displayYear) final standings")
                                .font(.caption)
                        }
                        .foregroundStyle(.secondary)
                        .padding(.horizontal)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    // Four-segment picker
                    Picker("Standings", selection: $segment) {
                        Text("Drivers").tag(0)
                        Text("Constructors").tag(1)
                        Text("Predictions").tag(2)
                        Text("Championship").tag(3)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)

                    switch segment {
                    case 0:
                        if vm.isLoading {
                            ProgressView("Loading standings...").padding(.top, 60)
                        } else if let error = vm.error {
                            ContentUnavailableView {
                                Label("Failed to Load", systemImage: "exclamationmark.triangle")
                            } description: {
                                Text(error)
                            } actions: {
                                Button("Retry") { Task { await vm.loadStandings() } }
                                    .buttonStyle(.borderedProminent).tint(.red)
                            }
                        } else {
                            DriverStandingsView(drivers: vm.drivers)
                        }
                    case 1:
                        if vm.isLoading {
                            ProgressView("Loading standings...").padding(.top, 60)
                        } else if let error = vm.error {
                            ContentUnavailableView {
                                Label("Failed to Load", systemImage: "exclamationmark.triangle")
                            } description: {
                                Text(error)
                            } actions: {
                                Button("Retry") { Task { await vm.loadStandings() } }
                                    .buttonStyle(.borderedProminent).tint(.red)
                            }
                        } else {
                            ConstructorStandingsView(constructors: vm.constructors)
                        }
                    case 2: // Predictions
                        PredictionsView(
                            upcomingRace: calVm.schedule.first(where: { $0.raceStatus == .upcoming }),
                            year: calVm.selectedYear
                        )
                    case 3: // Championship
                        ChampionshipView(year: vm.selectedYear)
                    default:
                        EmptyView()
                    }
                }
                .padding(.top, 8)
            }
            .navigationTitle("Standings")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    yearPicker
                }
            }
            .task {
                async let standings: () = {
                    if vm.drivers.isEmpty { await vm.loadStandings() }
                }()
                async let schedule: () = {
                    if calVm.schedule.isEmpty { await calVm.loadSchedule() }
                }()
                _ = await (standings, schedule)
            }
            .refreshable {
                await vm.loadStandings()
            }
        }
    }

    private var yearPicker: some View {
        Menu {
            ForEach(2021...2026, id: \.self) { year in
                Button {
                    vm.changeYear(year)
                } label: {
                    if year == vm.selectedYear {
                        Label("\(String(year))", systemImage: "checkmark")
                    } else {
                        Text(String(year))
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(String(vm.selectedYear))
                    .font(.system(size: 14, weight: .bold))
                Image(systemName: "chevron.down")
                    .font(.system(size: 10))
            }
            .foregroundStyle(.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(.ultraThinMaterial, in: Capsule())
        }
    }
}
