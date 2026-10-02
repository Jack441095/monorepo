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

    // run() discards output; trash() needs the sidecar's stdout to
    // find the undo-log path it prints, so this variant keeps it.
    // stdout is drained before waitUntilExit so a long table cannot
    // fill the pipe buffer and deadlock the run.
    private func runCapturing(_ exe: URL, args: [String]) -> (Int32, String) {
        let p = Process()
        p.executableURL = exe
        p.arguments = args
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
            let data = out.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            return (p.terminationStatus, String(data: data, encoding: .utf8) ?? "")
        } catch {
            DispatchQueue.main.async { self.statusLine = "Failed to launch \(exe.lastPathComponent): \(error)" }
            return (-1, "")
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
        let pickedPaths = Set(picks.map(\.path))
        statusLine = "Moving \(picks.count) items to Trash…"
        DispatchQueue.global(qos: .userInitiated).async {
            // The sidecar's --trash re-classifies the scan file it is
            // handed, so we filter the scanner's own rows down to the
            // checked paths: real categories and mtimes keep the
            // verdicts identical to what the UI showed, where rebuilt
            // rows would all classify as REVIEW "Other" and move
            // nothing without --include-review.
            var pickedLines: [String] = []
            if let scanText = try? String(contentsOf: self.scanJSONL, encoding: .utf8) {
                for line in scanText.split(separator: "\n") {
                    guard let row = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
                          let path = row["path"] as? String, pickedPaths.contains(path) else { continue }
                    pickedLines.append(String(line))
                }
            }
            guard pickedLines.count == picks.count else {
                DispatchQueue.main.async {
                    self.statusLine = "Scan file lost \(picks.count - pickedLines.count) picks — run Dry Run again before trashing."
                }
                return
            }
            let picksFile = FileManager.default.temporaryDirectory.appendingPathComponent("disksweep-picks.jsonl")
            do {
                try (pickedLines.joined(separator: "\n") + "\n").write(to: picksFile, atomically: true, encoding: .utf8)
            } catch {
                DispatchQueue.main.async { self.statusLine = "Cannot write picks file: \(error)" }
                return
            }
            let py = URL(fileURLWithPath: "/usr/bin/python3")
            let sidecar = self.bundleBin("sidecar").path + "/cli.py"
            var args = [sidecar, "--scan", picksFile.path, "--no-llm", "--trash"]
            if picks.contains(where: { $0.safety == "REVIEW" }) {
                // A ticked REVIEW box is the human approval that
                // --include-review exists for; SAFE picks move without it.
                args.append("--include-review")
            }
            let (status, output) = self.runCapturing(py, args: args)
            guard status >= 0 else { return }  // launch failure already posted
            // The undo log is the sidecar's record of what actually
            // moved; skipped items (already gone, EPERM) never reach it.
            var logPath: String?
            if let r = output.range(of: "Moved to Trash. Undo log: ") {
                logPath = output[r.upperBound...]
                    .split(separator: "\n").first.map(String.init)?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
            var moved = 0
            if let logPath = logPath,
               let data = try? Data(contentsOf: URL(fileURLWithPath: logPath)),
               let entries = try? JSONDecoder().decode([[String: String]].self, from: data) {
                moved = entries.count
            }
            let failed = picks.count - moved
            DispatchQueue.main.async {
                self.undoLog = logPath
                self.statusLine = failed == 0
                    ? "Moved \(moved) items to Trash. Undo restores from ~/.Trash/Disksweep."
                    : "Moved \(moved) of \(picks.count) items to Trash, \(failed) failed."
                self.dryRun() // rescan to refresh
            }
        }
    }
}
