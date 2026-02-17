import SwiftUI

struct CalendarTab: View {
    @Binding var mainTab: Int
    @State private var vm = CalendarViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading {
                    ProgressView("Loading schedule...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = vm.error {
                    ContentUnavailableView {
                        Label("Failed to Load", systemImage: "exclamationmark.triangle")
                    } description: {
                        Text(error)
                    } actions: {
                        Button("Retry") { Task { await vm.loadSchedule() } }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                    }
                } else {
                    raceList
                }
            }
            .navigationTitle("Calendar")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    yearPicker
                }
            }
            .task {
                if vm.schedule.isEmpty {
                    await vm.loadSchedule()
                }
            }
            .refreshable {
                await vm.loadSchedule()
            }
        }
    }

    private var raceList: some View {
        List(vm.schedule) { race in
            NavigationLink(value: race) {
                RaceRow(race: race, countdown: vm.countdown(for: race))
            }
            .listRowBackground(
                race.round == vm.currentRace?.round
                    ? Color.red.opacity(0.05)
                    : Color.clear
            )
        }
        .listStyle(.plain)
        .navigationDestination(for: RaceEvent.self) { race in
            RaceDetailView(race: race, year: vm.selectedYear, mainTab: $mainTab)
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
