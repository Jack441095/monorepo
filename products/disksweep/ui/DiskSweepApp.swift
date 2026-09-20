// DiskSweep SwiftUI skeleton — build with Xcode 16+ (macOS 14+).
// Target: macOS app "DiskSweep". Bundle the C++ scanner binary +
// sidecar/ tree inside Resources; this UI shells out to them.
// No networking except localhost Ollama (handled inside sidecar).
import SwiftUI

@main
struct DiskSweepApp: App {
    @StateObject private var store = ScanStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .frame(minWidth: 980, minHeight: 560)
        }
        .commands {
            CommandGroup(after: .toolbar) {
                Button("Dry Run") { store.dryRun() }
                    .keyboardShortcut("r", modifiers: .command)
                Button("Move to Trash") { store.trash() }
                    .keyboardShortcut("t", modifiers: [.command, .shift])
                    .disabled(!store.canTrash)
            }
        }
    }
}
