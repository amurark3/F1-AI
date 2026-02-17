import SwiftUI

struct StandingsTab: View {
    @State private var vm = StandingsViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Driver/Constructor toggle
                    Picker("Standings", selection: $vm.showingDrivers) {
                        Text("Drivers").tag(true)
                        Text("Constructors").tag(false)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)

                    if vm.isLoading {
                        ProgressView("Loading standings...")
                            .padding(.top, 60)
                    } else if let error = vm.error {
                        ContentUnavailableView {
                            Label("Failed to Load", systemImage: "exclamationmark.triangle")
                        } description: {
                            Text(error)
                        } actions: {
                            Button("Retry") { Task { await vm.loadStandings() } }
                                .buttonStyle(.borderedProminent)
                                .tint(.red)
                        }
                    } else if vm.showingDrivers {
                        DriverStandingsView(drivers: vm.drivers)
                    } else {
                        ConstructorStandingsView(constructors: vm.constructors)
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
                if vm.drivers.isEmpty {
                    await vm.loadStandings()
                }
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
