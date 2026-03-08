import SwiftUI
import UserNotifications

struct NotificationSettingsView: View {
    // Advance minutes via @AppStorage (SwiftUI-native UserDefaults wrapper)
    @AppStorage("notificationAdvanceMinutes") private var advanceMinutes: Int = 15
    // Favorite driver abbreviation for Dynamic Island live tracking
    @AppStorage("favoriteDriver") private var favoriteDriver: String = ""

    // Per-session toggle state — loaded from UserDefaults, saved on change
    @State private var enabledSessions: Set<String> = UserDefaults.standard.enabledNotificationSessions
    @State private var permissionStatus: UNAuthorizationStatus = .notDetermined

    // Readable display names for the settings UI
    private let sessionDisplayLabels: [(key: String, label: String)] = [
        ("Practice 1",        "FP1 (Practice 1)"),
        ("Practice 2",        "FP2 (Practice 2)"),
        ("Practice 3",        "FP3 (Practice 3)"),
        ("Qualifying",        "Qualifying"),
        ("Sprint Qualifying", "Sprint Qualifying"),
        ("Sprint",            "Sprint Race"),
        ("Race",              "Race"),
    ]

    var body: some View {
        NavigationStack {
            Form {
                // Live race tracking — favorite driver for Dynamic Island
                Section {
                    TextField("Driver abbreviation (e.g. VER)", text: $favoriteDriver)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.characters)
                } header: {
                    Text("Live Race Tracking")
                } footer: {
                    Text("Dynamic Island tracks this driver during live sessions. Leave blank to track the race leader.")
                }

                // Advance notice picker
                Section {
                    Picker("Notify me", selection: $advanceMinutes) {
                        Text("5 minutes before").tag(5)
                        Text("15 minutes before").tag(15)
                        Text("30 minutes before").tag(30)
                    }
                    .pickerStyle(.inline)
                } header: {
                    Text("Advance Notice")
                } footer: {
                    Text("How early to be notified before each session starts.")
                }

                // Per-session toggles
                Section {
                    ForEach(sessionDisplayLabels, id: \.key) { item in
                        Toggle(item.label, isOn: Binding(
                            get: { enabledSessions.contains(item.key) },
                            set: { isOn in
                                if isOn {
                                    enabledSessions.insert(item.key)
                                } else {
                                    enabledSessions.remove(item.key)
                                }
                                UserDefaults.standard.enabledNotificationSessions = enabledSessions
                            }
                        ))
                    }
                } header: {
                    Text("Session Types")
                } footer: {
                    Text("Select which sessions trigger a notification.")
                }

                // Permission status warning
                if permissionStatus == .denied {
                    Section {
                        Label("Notifications are disabled in Settings. Enable them to receive session alerts.", systemImage: "bell.slash")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Notifications")
            .navigationBarTitleDisplayMode(.inline)
            .task {
                let settings = await UNUserNotificationCenter.current().notificationSettings()
                permissionStatus = settings.authorizationStatus
            }
            // When advance minutes changes, the advanceMinutes @AppStorage binding updates UserDefaults automatically.
            // No explicit save needed for advance minutes. Session toggles save inline in the Binding set closure.
        }
    }
}
