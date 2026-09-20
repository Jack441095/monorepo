// First-run Full Disk Access onboarding sheet.
import SwiftUI

struct FullDiskAccessView: View {
    @Environment(\.openURL) private var openURL
    @Binding var isPresented: Bool

    private var hasAccess: Bool {
        // Same heuristic as `doctor`: TCC.db readable implies FDA granted.
        let tcc = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/com.apple.TCC/TCC.db")
        return FileManager.default.isReadableFile(atPath: tcc.path)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Full Disk Access").font(.title2.bold())
            Text("DiskSweep scans your Caches, Application Support, Mail containers and developer "
                + "caches. Without Full Disk Access those rows silently read as empty.")
                .foregroundStyle(.secondary)
            if hasAccess {
                Label("Access granted — you're set.", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else {
                Label("Access not detected.", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Button("Open Settings > Privacy > Full Disk Access") {
                    openURL(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy")!)
                }
                Text("Tick DiskSweep, then press Rescan. The scanner stays read-only either way.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button(hasAccess ? "Done" : "Skip for now") { isPresented = false }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20).frame(width: 480)
    }
}
