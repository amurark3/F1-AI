import SwiftUI
import UserNotifications

struct CalendarTab: View {
    @Binding var mainTab: Int
    @State private var vm = CalendarViewModel()
    @State private var showingSettings = false

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
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        showingSettings = true
                    } label: {
                        Image(systemName: "gear")
                            .foregroundStyle(.primary)
                    }
                    .sheet(isPresented: $showingSettings) {
                        NotificationSettingsView()
                            .presentationDetents([.medium, .large])
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    yearPicker
                }
            }
            .task {
                if vm.schedule.isEmpty {
                    await vm.loadSchedule()
                }
                // Request notification permission on first load if not yet determined
                let center = UNUserNotificationCenter.current()
                let settings = await center.notificationSettings()
                if settings.authorizationStatus == .notDetermined {
                    _ = await NotificationService.shared.requestPermission()
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
