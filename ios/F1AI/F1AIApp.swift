import SwiftUI
import SwiftData

@main
struct F1AIApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
        .modelContainer(for: CachedResponse.self)
    }
}

struct ContentView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            PitWallTab()
                .tag(0)
                .tabItem {
                    Label("Pit Wall", systemImage: "headphones")
                }

            LiveTab()
                .tag(1)
                .tabItem {
                    Label("Live", systemImage: "antenna.radiowaves.left.and.right")
                }

            CalendarTab(mainTab: $selectedTab)
                .tag(2)
                .tabItem {
                    Label("Calendar", systemImage: "flag.checkered")
                }

            DriverCompareView()
                .tag(3)
                .tabItem {
                    Label("H2H", systemImage: "person.2.fill")
                }

            StandingsTab()
                .tag(4)
                .tabItem {
                    Label("Standings", systemImage: "trophy.fill")
                }
        }
        .tint(.red)
    }
}
