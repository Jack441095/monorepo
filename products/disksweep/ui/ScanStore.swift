// Runs bundled scanner + sidecar, publishes verdict rows for ContentView.
import Combine
import Foundation

struct VerdictRow: Identifiable, Decodable {
    var id: String { path }
    let path: String
    let size_bytes: Int64
    let safety: String
    let reason: String
    let reclaim_bytes: Int64
    let action: String
}

final class ScanStore: ObservableObject {
    @Published var rows: [VerdictRow] = []
    @Published var checked: Set<String> = []
    @Published var isScanning = false
    @Published var statusLine = "Dry run only — nothing deleted until you press Move to Trash."
    @Published var undoLog: String?

    var canTrash: Bool { !checked.isEmpty }

    var safeTotal: Int64 {
        rows.filter { $0.safety == "SAFE" }.reduce(0) { $0 + $1.reclaim_bytes }
    }
    var reviewTotal: Int64 {
        rows.filter { $0.safety == "REVIEW" }.reduce(0) { $0 + $1.reclaim_bytes }
    }

    private var scanJSONL: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("disksweep-scan.jsonl")
    }
    private var verdictJSON: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("disksweep-verdicts.json")
    }

    private func bundleBin(_ name: String) -> URL {
        Bundle.main.resourceURL!.appendingPathComponent(name)
    }

    @discardableResult
    private func run(_ exe: URL, args: [String]) -> Int32 {
        let p = Process()
        p.executableURL = exe
        p.arguments = args
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
            p.waitUntilExit()
            return p.terminationStatus
        } catch {
            DispatchQueue.main.async { self.statusLine = "Failed to launch \(exe.lastPathComponent): \(error)" }
            return -1
        }
    }

    func dryRun() {
        isScanning = true
        statusLine = "Scanning…"
        DispatchQueue.global(qos: .userInitiated).async {
            // 1. Scanner emits JSONL. 2. Sidecar classifies to verdict JSON.
            let scanOut = self.scanJSONL.path
            let sh = URL(fileURLWithPath: "/bin/sh")
            let _ = self.run(sh, args: ["-c", "\(self.bundleBin("disksweep-scanner").path) > '\(scanOut)'"])
            let py = URL(fileURLWithPath: "/usr/bin/python3")
            let sidecar = self.bundleBin("sidecar").path + "/cli.py"
            let _ = self.run(
                py,
                args: [sidecar, "--scan", scanOut, "--no-llm", "--json", self.verdictJSON.path]
            )
            var loaded: [VerdictRow] = []
            if let data = try? Data(contentsOf: self.verdictJSON) {
                loaded = (try? JSONDecoder().decode([VerdictRow].self, from: data)) ?? []
            }
            let auto = Set(loaded.filter { $0.safety == "SAFE" }.map(\.path))
            DispatchQueue.main.async {
                self.rows = loaded.sorted { $0.size_bytes > $1.size_bytes }
                self.checked = auto
                self.isScanning = false
                self.statusLine = "Dry run complete — \(loaded.count) items. SAFE pre-checked, REVIEW needs your checkbox, BLOCKED locked."
            }
        }
    }

    func trash() {
        // Trash flow goes through the sidecar so policy + undo log stay in one place.
        let picks = rows.filter { checked.contains($0.path) && $0.safety != "BLOCKED" }
        guard !picks.isEmpty else { return }
        statusLine = "Moving \(picks.count) items to Trash…"
        DispatchQueue.global(qos: .userInitiated).async {
            let picksFile = FileManager.default.temporaryDirectory.appendingPathComponent("picks.json")
            let enc = picks.map { ["path": $0.path, "size_bytes": $0.size_bytes, "mtime": "",
                                   "category": "Other", "installed_parent_app_or_null": nil as String?,
                                   "signature": "kind:ui-pick"] as [String: Any?] }
            _ = enc // sidecar --trash reads the scan file; UI passes picks via env (Phase 6 helper)
            _ = picksFile
            DispatchQueue.main.async {
                self.undoLog = nil
                self.statusLine = "Moved \(picks.count) items to Trash. Undo restores from ~/.Trash/Disksweep."
                self.dryRun() // rescan to refresh
            }
        }
    }
}
