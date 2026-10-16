import ApplicationServices
import Darwin
import Foundation

private struct TestFailure: Error, CustomStringConvertible {
    let description: String
}

private func expect(_ condition: @autoclosure () -> Bool, _ reason: String) throws {
    if !condition() { throw TestFailure(description: reason) }
}

private func rejects(_ body: () throws -> Void, _ reason: String) throws {
    do { try body() } catch { return }
    throw TestFailure(description: reason)
}

/// A complete synthetic Live window transition; no fixture calls native AX or opens a real application.
private final class ExportCallerFixture {
    private static var nextPID = Int32.max - 1_000 // Distinct fake identities prevent cross-instance ownership by accident.
    let request: LiveExportRequest
    let scenario: String
    let start = Date(timeIntervalSince1970: 2_000)
    var clock = Date(timeIntervalSince1970: 2_000)
    var menuPresses = 0
    var cancelPresses = 0
    var otherPresses = 0
    var visible = false
    var sleeps = 0
    var error: Error?
    private var cleaning = false
    private var enabledReads = 0
    private var processReads = 0
    private var trustReads = 0
    private var profileRead = false
    private let nodes: [AXUIElement]
    private let settings: [(String, String, AXUIElement)]
    private var main: AXUIElement { nodes[0] }
    private var dialog: AXUIElement { nodes[1] }
    private var menuBar: AXUIElement { nodes[2] }
    private var file: AXUIElement { nodes[3] }
    private var menu: AXUIElement { nodes[4] }
    private var export: AXUIElement { nodes[5] }
    private var cancel: AXUIElement { nodes[6] }
    private var replacementMain: AXUIElement { nodes[7] }
    private var foreign: AXUIElement { nodes[8] }
    private var replacementCancel: AXUIElement { nodes[9] }
    private var replacementDialog: AXUIElement { nodes[10] }
    private var marker: URL { URL(fileURLWithPath: request.output_path).deletingLastPathComponent().appendingPathComponent("cancel.requested") }
    var elapsed: TimeInterval { clock.timeIntervalSince(start) }

    init(request: LiveExportRequest, scenario: String) {
        self.request = request
        self.scenario = scenario
        func node() -> AXUIElement {
            Self.nextPID -= 1
            return AXUIElementCreateApplication(Self.nextPID)
        }
        nodes = (0..<11).map { _ in node() }
        var values = LiveExportProfile.fixedSettings
        for (prefix, position) in [("Base.RenderStartBox.RenderStart", request.render_start), ("Base.RenderLengthBox.RenderLength", request.render_length)] {
            for (component, number) in zip(["Bars", "Beats", "Subdivisions"], position.split(separator: ".")) {
                values["\(prefix).\(component)"] = String(Int(number)!)
            }
        }
        settings = values.keys.sorted().map { ($0, values[$0]!, node()) }
    }

    func removeMarker() {
        // lstat also finds a dangling cancellation link; following it would leave the next fixture cancelled.
        var info = stat()
        do { if lstat(marker.path, &info) == 0 { try FileManager.default.removeItem(at: marker) } }
        catch { self.error = error } // The test checks fixture I/O separately from production rejection.
    }

    private func writeMarker(brokenLink: Bool = false) {
        do {
            if brokenLink { try FileManager.default.createSymbolicLink(atPath: marker.path, withDestinationPath: marker.path + ".missing") }
            else { try Data().write(to: marker) }
        } catch { self.error = error }
    }

    private func windows() -> [AXUIElement] {
        if scenario == "duplicate-windows" { return [main, main] }
        let replaced = (scenario == "replaced-main" && menuPresses > 0) || (scenario == "cleanup-main" && cleaning)
        var result = [replaced ? replacementMain : main]
        if scenario == "existing-dialog" { result.append(dialog); return result }
        let delayed = scenario == "cancel-delayed" && elapsed < 0.3
        if visible && !delayed {
            let replacedDialog = (scenario == "cleanup-replaced-dialog" && cleaning) || (scenario == "close-replacement" && cancelPresses > 0)
            result.append(replacedDialog ? replacementDialog : dialog)
        }
        if (scenario == "ambiguous-dialog" && menuPresses > 0) || (scenario == "extra-window" && menuPresses > 0) || (["cleanup-extra-dialog", "cleanup-extra-window"].contains(scenario) && cleaning) {
            result.append(foreign)
        }
        return result
    }

    private func children(_ node: AXUIElement) -> [AXUIElement] {
        if CFEqual(node, menuBar) { return [file] }
        if CFEqual(node, file) { return [menu] }
        if CFEqual(node, menu) { return [export] }
        if CFEqual(node, dialog) || CFEqual(node, replacementDialog) {
            let button = cleaning && scenario == "cleanup-replaced-cancel" ? replacementCancel : cancel
            return (scenario == "missing-cancel" ? [] : [button]) + settings.map { $0.2 }
        }
        return [] // Main, foreign window and all controls are complete leaves in this fixture.
    }

    private func value(_ node: AXUIElement, _ key: String) -> (AXError, CFTypeRef?) {
        if key == kAXMenuBarAttribute {
            if scenario == "broken-marker-before-menu" { writeMarker(brokenLink: true) }
            return (.success, menuBar)
        }
        if key == kAXTitleAttribute {
            if CFEqual(node, main) || CFEqual(node, replacementMain) { return (.success, request.expected_window_title as CFString) }
            if CFEqual(node, dialog) || CFEqual(node, replacementDialog) { return (.success, (scenario == "foreign-dialog" ? "Unrelated dialog" : "Export Audio/Video") as CFString) }
            if CFEqual(node, file) { return (.success, "File" as CFString) }
            if CFEqual(node, export) { return (.success, "Export Audio/Video…" as CFString) }
        }
        if key == kAXRoleAttribute {
            if CFEqual(node, main), scenario == "main-role" { return (.success, kAXButtonRole as CFString) }
            if CFEqual(node, main), scenario == "main-role-absent" { return (.noValue, nil) }
            if [main, replacementMain, dialog, replacementDialog, foreign].contains(where: { CFEqual($0, node) }) { return (.success, kAXWindowRole as CFString) }
            if CFEqual(node, cancel) || CFEqual(node, replacementCancel) { return (.success, (cleaning && scenario == "cleanup-role" ? kAXTextFieldRole : kAXButtonRole) as CFString) }
            return (.success, kAXTextFieldRole as CFString)
        }
        if key == kAXSubroleAttribute {
            if CFEqual(node, main), scenario == "main-subrole" { return (.success, kAXDialogSubrole as CFString) }
            if CFEqual(node, main), scenario == "main-subrole-absent" { return (.noValue, nil) }
            let isDialog = [dialog, replacementDialog].contains(where: { CFEqual($0, node) }) || (CFEqual(node, foreign) && !["extra-window", "cleanup-extra-window"].contains(scenario))
            return (.success, (isDialog ? kAXDialogSubrole : kAXStandardWindowSubrole) as CFString)
        }
        if key == kAXIdentifierAttribute {
            if CFEqual(node, cancel) || CFEqual(node, replacementCancel) { return (.success, (cleaning && scenario == "cleanup-identifier" ? "Unrelated.Cancel" : "Base.FinalButtonsBox.CancelButton") as CFString) }
            if let setting = settings.first(where: { CFEqual($0.2, node) }) { return (.success, setting.0 as CFString) }
        }
        if key == kAXEnabledAttribute, CFEqual(node, cancel) || CFEqual(node, replacementCancel) {
            enabledReads += 1
            if cleaning && scenario == "cleanup-boolean" { return (.success, NSNumber(value: 1)) }
            return (.success, cleaning && scenario == "cleanup-disabled" ? kCFBooleanFalse : kCFBooleanTrue)
        }
        if key == kAXValueAttribute, let setting = settings.first(where: { CFEqual($0.2, node) }) {
            if !profileRead {
                profileRead = true
                if scenario == "cancel-profile" { writeMarker() }
                if scenario == "deadline-profile" { clock = start.addingTimeInterval(Double(request.timeout_seconds)) }
            }
            return (.success, setting.1 as CFString)
        }
        return (.noValue, nil) // Absent optional attributes carry no ownership or control evidence.
    }

    var environment: LiveExportEnvironment {
        LiveExportEnvironment(trusted: {
            self.trustReads += 1
            return !(self.scenario == "trust-before-menu" && self.trustReads >= 3) && !(self.scenario == "cleanup-trust" && self.cleaning) && !(self.scenario == "cleanup-last-trust" && self.trustReads == 7)
        }, isLive: { _ in
            self.processReads += 1
            return !(self.scenario == "process-before-menu" && self.processReads >= 2) && !(self.scenario == "cleanup-process" && self.cleaning) && !(self.scenario == "cleanup-last-process" && self.processReads == 6)
        }, reader: { deadline in
            // Caller and reader share one fake clock. A new cleanup deadline follows successful Cancel acquisition.
            if self.enabledReads > 0 && deadline != self.start.addingTimeInterval(Double(self.request.timeout_seconds)) { self.cleaning = true }
            return ExportAXReader(deadline: deadline, now: { self.clock }, copyValue: { self.value($0, $1) }, countValues: { node, key in
                if key == kAXWindowsAttribute {
                    if self.scenario == "cancel-late-acquisition", self.menuPresses > 0 {
                        self.clock = deadline // An AX operation can return only after the shortened acceptance deadline.
                    }
                    if (self.scenario == "cleanup-read-failed" && self.cleaning) || (self.scenario == "close-read-failed" && self.cancelPresses > 0) { return (.cannotComplete, 0) }
                    return (.success, self.windows().count)
                }
                return (.success, self.children(node).count)
            }, copyValues: { node, key, _ in (.success, (key == kAXWindowsAttribute ? self.windows() : self.children(node)) as CFArray) })
        }, press: { node in
            if CFEqual(node, self.export) {
                self.menuPresses += 1
                self.visible = !["never-appears", "cancel-never-appears", "cancel-late-acquisition"].contains(self.scenario)
                if ["cancel-never-appears", "cancel-delayed", "cancel-late-acquisition"].contains(self.scenario) { self.writeMarker() }
                if self.scenario == "deadline-acquisition" { self.clock = self.start.addingTimeInterval(Double(self.request.timeout_seconds)) }
                return .success
            }
            if CFEqual(node, self.cancel) {
                self.cancelPresses += 1
                if self.scenario == "cancel-rejected" { return .failure }
                if !["cancel-stuck", "close-replacement"].contains(self.scenario) { self.visible = false }
                return .success
            }
            self.otherPresses += 1
            return .failure // Export/Save and every unrelated control are forbidden even in the positive fixture.
        }, now: { self.clock }, sleep: { seconds in
            self.sleeps += 1
            self.clock = self.clock.addingTimeInterval(seconds)
        })
    }
}

@main
struct LiveExportHelperTests {
    static func main() {
        do { try run() } catch {
            // Return a test failure instead of trapping, so mutation checks do not produce crash reports.
            FileHandle.standardError.write(Data("FAIL: \(error)\n".utf8))
            exit(1)
        }
    }

    private static func run() throws {
        try axReadsRejectFailuresAndTruncation()
        let root = URL(fileURLWithPath: canonicalPath(FileManager.default.temporaryDirectory.path)!).appendingPathComponent("kenn-export-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) } // Tests remove only their exclusive generated fixture directory.
        func request(path: String? = nil, action: String = "export", sampleRate: Int = 48_000, start: String = "1.1.1", length: String = "32.0.0") -> LiveExportRequest {
            LiveExportRequest(schema: "kenn.live_export_request.v1", action: action, live_pid: getpid(), expected_window_title: "Disposable Test Set", output_path: path ?? root.appendingPathComponent("kenn-analysis.wav").path, render_start: start, render_length: length, sample_rate: sampleRate, timeout_seconds: 10)
        }
        let original = request()
        try original.validate()
        try incompletePreflightNeverPressesExport(original)
        try cancellationAfterMenuClosesOnlyTheNewExportDialog(original)
        try actualCallerOwnsAndCancelsOnlyQualifiedTransitions(original)
        try saveDestinationRequiresExactReadOnlyEvidence(request: original, root: root)
        for name in ["manifest.json", "receipt.json", "cancel.requested"] {
            try Data("{}".utf8).write(to: root.appendingPathComponent(name))
        }
        try original.validate()
        for name in ["manifest.json", "receipt.json", "cancel.requested"] {
            try FileManager.default.removeItem(at: root.appendingPathComponent(name))
        }
        try rejects({ try request(sampleRate: 44_100).validate() }, "An unqualified sample rate was accepted")
        try rejects({ try request(start: "1.1.1 ").validate() }, "A range with ambiguous whitespace was accepted")
        try rejects({ try request(length: "0.0.0").validate() }, "A zero-length arrangement was accepted")
        for position in ["1.100.1", "1.1.100", "١.١.١", "１.１.１"] {
            // Python and Swift must authorize the same exact ASCII musical range.
            try rejects({ try request(start: position).validate() }, "An out-of-contract musical range was accepted: \(position)")
        }
        try rejects({ try request(start: "0.1.1").validate() }, "A zero start bar was accepted")
        try rejects({ try request(length: "00.00.00").validate() }, "A padded zero-length arrangement was accepted")
        try request(start: "000001.01.01", length: "0.00.01").validate()
        try request(start: "999999.99.99", length: "999999.99.99").validate()
        try rejects({ try request(path: root.appendingPathComponent("other.wav").path).validate() }, "An arbitrary output filename was accepted")
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: root.path)
        try rejects({ try original.validate() }, "A shared job directory was accepted")
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: root.path)
        let output = URL(fileURLWithPath: original.output_path)
        try Data([1]).write(to: output)
        try rejects({ try original.validate() }, "An existing user file was accepted for overwrite")
        try FileManager.default.removeItem(at: output)
        let foreign = root.appendingPathComponent("unrelated.wav")
        try Data([2]).write(to: foreign)
        try rejects({ try original.validate() }, "A nonexclusive directory was accepted")
        try FileManager.default.removeItem(at: foreign)
        try FileManager.default.createSymbolicLink(atPath: original.output_path, withDestinationPath: "/dev/null")
        try rejects({ try original.validate() }, "An output symbolic link was accepted")
        try FileManager.default.removeItem(at: output)

        // The production gate must stop before asking AX for process state or performing a menu action.
        let disabled = LiveExportAccessibility(original).run(supervised: false, enabled: true)
        try expect(disabled.error_code == "experimental_export_disabled", "The supervised flag did not gate export")
        let noEnvironment = LiveExportAccessibility(original).run(supervised: true, enabled: false)
        try expect(noEnvironment.error_code == "experimental_export_disabled", "The environment gate did not gate export")
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(disabled)) as! [String: Any]
        try expect(encoded["live_pid"] as? Int == Int(getpid()), "A failed receipt lost the requested writer identity")
        try expect(encoded["output_path"] as? String == original.output_path, "A failed receipt lost the exact output path")
        try expect(!disabled.writer_closed, "A failed receipt claimed writer closure")

        var profile = LiveExportProfile.fixedSettings.mapValues { [$0] }
        for (prefix, components) in [("Base.RenderStartBox.RenderStart", ["1", "1", "1"]),
                                     ("Base.RenderLengthBox.RenderLength", ["32", "0", "0"])] {
            for (component, number) in zip(["Bars", "Beats", "Subdivisions"], components) {
                profile["\(prefix).\(component)"] = [number]
            }
        }
        try LiveExportProfile.validate(values: profile, request: original)
        let toggle = "Base.EncodeMp3Box.EncodeMp3"
        try expect(LiveExportProfile.settingValue(identifier: toggle, value: NSNumber(value: 0)) == "Off", "Exact zero did not read back as Off")
        try expect(LiveExportProfile.settingValue(identifier: toggle, value: NSNumber(value: 1)) == "On", "Exact one did not read back as On")
        for value in [-1.0, 0.5, 1.5, 2.0, Double.nan] {
            // AX fractions must not truncate into a qualified On/Off preference.
            let setting = LiveExportProfile.settingValue(identifier: toggle, value: NSNumber(value: value))
            try expect(!["Off", "On"].contains(setting), "An ambiguous numeric preference became On/Off")
        }
        try expect(LiveExportProfile.settingValue(identifier: "Base.SampleRateBox.SampleRate", value: NSNumber(value: 1)) == "1", "A non-toggle setting became On")
        profile["Base.EncodeMp3Box.EncodeMp3"] = ["On"]
        try rejects({ try LiveExportProfile.validate(values: profile, request: original) }, "MP3 output was silently accepted")
        profile["Base.EncodeMp3Box.EncodeMp3"] = ["Off"]
        profile["Base.RenderLengthBox.RenderLength.Bars"] = ["31"]
        try rejects({ try LiveExportProfile.validate(values: profile, request: original) }, "A different render range was accepted")
        profile["Base.RenderLengthBox.RenderLength.Bars"] = ["32", "32"]
        try rejects({ try LiveExportProfile.validate(values: profile, request: original) }, "An ambiguous range control was accepted")
        profile.removeValue(forKey: "Base.RenderLengthBox.RenderLength.Bars")
        try rejects({ try LiveExportProfile.validate(values: profile, request: original) }, "An inaccessible range control was accepted")

        try wavAndDescriptorEvidenceShareOneGeneration(output: output, root: root)
        let valid = wav()
        try valid.write(to: output)
        try ExportWAV.validate(output.path)
        let alias = root.appendingPathComponent("linked-output.wav")
        try FileManager.default.linkItem(at: output, to: alias)
        try rejects({ try ExportWAV.validate(output.path) }, "A hard-linked WAV was accepted as exclusively owned")
        try FileManager.default.removeItem(at: alias)
        let identity = try ExportWAV.validate(output.path)
        let handle = try FileHandle(forWritingTo: output)
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: identity)?.hasNoOpenDescriptor == false, "An open writer descriptor was missed")
        try handle.close()
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: identity)?.hasNoOpenDescriptor == true, "The closed self-process descriptor could not be verified")
        try Data(valid.dropLast()).write(to: output)
        try rejects({ try ExportWAV.validate(output.path) }, "A partial file was treated as a completed WAV")
        try wav(sampleRate: 44_100).write(to: output)
        try rejects({ try ExportWAV.validate(output.path) }, "Wrong-rate WAV evidence was accepted")
        try wav(channels: 1).write(to: output)
        try rejects({ try ExportWAV.validate(output.path) }, "A mono WAV was accepted as stereo evidence")
        // Sparse fixtures exercise the eight-minute boundary without allocating audio-sized buffers.
        for (frames, accepted) in [(UInt32(48_000 * 8 * 60), true), (UInt32(48_000 * 8 * 60 + 1), false)] {
            try wav(frames: frames).write(to: output)
            let sparse = try FileHandle(forWritingTo: output)
            try sparse.truncate(atOffset: UInt64(frames) * 6 + 44)
            try sparse.close()
            if accepted {
                try ExportWAV.validate(output.path)
            } else {
                try rejects({ try ExportWAV.validate(output.path) }, "A WAV longer than eight minutes was accepted")
            }
        }
        let oversized = try FileHandle(forWritingTo: output)
        try oversized.truncate(atOffset: ExportWAV.maximumBytes + 1)
        try oversized.close()
        try rejects({ try ExportWAV.validate(output.path) }, "An over-limit sparse file was accepted")
        print("PASS: request ownership, double export gate, receipt identity, all completion gates, PCM validation and real descriptor closure")
    }

    private static func saveDestinationRequiresExactReadOnlyEvidence(request: LiveExportRequest, root: URL) throws {
        let job = root.appendingPathComponent("destination")
        let parked = root.appendingPathComponent("previous-destination")
        let other = root.appendingPathComponent("other-destination")
        try FileManager.default.createDirectory(at: other, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: other) } // This verifier test owns only its generated directories.
        let current = LiveExportRequest(schema: request.schema, action: request.action, live_pid: request.live_pid,
            expected_window_title: request.expected_window_title, output_path: job.appendingPathComponent("kenn-analysis.wav").path,
            render_start: request.render_start, render_length: request.render_length, sample_rate: request.sample_rate, timeout_seconds: request.timeout_seconds)
        let panel = AXUIElementCreateApplication(Int32.max - 20)
        let identifiers = ["saveAsNameTextField", "where popup", "CancelButton", "OKButton", "ColumnView"]
        let controls = identifiers.indices.map { AXUIElementCreateApplication(Int32.max - 21 - Int32($0)) }
        let extra = AXUIElementCreateApplication(Int32.max - 30)
        let roles = [kAXTextFieldRole, kAXPopUpButtonRole, kAXButtonRole, kAXButtonRole, kAXBrowserRole]
        let start = Date(timeIntervalSince1970: 1)
        var healthyReader: ExportAXReader?
        let failures = ["none", "wrong-directory", "string-url", "remote-url", "query-url", "missing-url", "failed-url",
                        "wrong-name", "missing-control", "duplicate-control", "duplicate-panel", "wrong-role", "disabled", "malformed-enabled",
                        "nested-sheet", "failed-role", "truncated-tree", "deadline", "late-url", "target-appeared", "cancel-appeared",
                        "metadata-appeared", "directory-replaced", "directory-mode"]
        for failure in failures {
            try FileManager.default.createDirectory(at: job, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            var clock = start
            var mutated = false
            var fixtureError: Error?
            func index(_ node: AXUIElement) -> Int? { controls.firstIndex { CFEqual($0, node) } }
            func children(_ node: AXUIElement) -> [AXUIElement] {
                guard CFEqual(node, panel) else { return [] } // The complete fixture tree has one panel and leaf controls.
                var result = controls
                if failure == "missing-control" { result.remove(at: 3) }
                if ["duplicate-control", "duplicate-panel", "nested-sheet"].contains(failure) { result.append(extra) }
                return result
            }
            let reader = ExportAXReader(deadline: failure == "deadline" ? start : start.addingTimeInterval(1), now: { clock }, copyValue: { node, key in
                if key == kAXRoleAttribute {
                    if failure == "failed-role" { return (.cannotComplete, nil) }
                    if CFEqual(node, panel) { return (.success, kAXSheetRole as CFString) }
                    if CFEqual(node, extra) { return (.success, (failure == "nested-sheet" ? kAXSheetRole : kAXGroupRole) as CFString) }
                    if let position = index(node) {
                        return (.success, (failure == "wrong-role" && position == 4 ? kAXGroupRole : roles[position]) as CFString)
                    }
                }
                if key == kAXIdentifierAttribute {
                    if CFEqual(node, panel) { return (.success, "save-panel" as CFString) }
                    if CFEqual(node, extra) {
                        let identifier = failure == "duplicate-panel" ? "save-panel" : (failure == "nested-sheet" ? "nested-sheet" : "OKButton")
                        return (.success, identifier as CFString)
                    }
                    if let position = index(node) { return (.success, identifiers[position] as CFString) }
                }
                if key == kAXEnabledAttribute {
                    if failure == "malformed-enabled" { return (.success, NSNumber(value: 1)) }
                    return (.success, failure == "disabled" ? kCFBooleanFalse : kCFBooleanTrue)
                }
                if key == kAXValueAttribute, let position = index(node) {
                    if position == 0 { return (.success, (failure == "wrong-name" ? "user-export.wav" : "kenn-analysis.wav") as CFString) }
                    // The popup's display name is deliberately unrelated; it cannot prove the target directory.
                    if position == 1 { return (.success, "Unrelated display name" as CFString) }
                }
                if key == kAXURLAttribute, CFEqual(node, controls[4]) {
                    if !mutated {
                        mutated = true
                        do {
                            if failure == "target-appeared" { try Data([1]).write(to: URL(fileURLWithPath: current.output_path)) }
                            if failure == "cancel-appeared" { try Data().write(to: job.appendingPathComponent("cancel.requested")) }
                            if failure == "metadata-appeared" { try Data(repeating: 0, count: 65_537).write(to: job.appendingPathComponent("receipt.json")) }
                            if failure == "directory-mode" { try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: job.path) }
                            if failure == "directory-replaced" {
                                try FileManager.default.moveItem(at: job, to: parked)
                                try FileManager.default.createDirectory(at: job, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
                            }
                        } catch {
                            fixtureError = error
                            return (.failure, nil) // The assertion below distinguishes a failed mutation from a rejected race.
                        }
                    }
                    if failure == "late-url" { clock = start.addingTimeInterval(2) }
                    if failure == "missing-url" { return (.noValue, nil) }
                    if failure == "failed-url" { return (.cannotComplete, nil) }
                    if failure == "string-url" { return (.success, job.absoluteString as CFString) }
                    let url: URL
                    if failure == "wrong-directory" { url = other }
                    else if failure == "remote-url" { url = URL(string: "https://example.invalid/destination")! }
                    else if failure == "query-url" { url = URL(string: job.absoluteString + "?other")! }
                    else { url = job }
                    return (.success, url as CFURL)
                }
                return (.noValue, nil) // This profile has no other required attributes or subroles.
            }, countValues: { node, _ in
                (.success, failure == "truncated-tree" && CFEqual(node, panel) ? ExportAXReader.maximumNodes + 1 : children(node).count)
            }, copyValues: { node, _, _ in (.success, children(node) as CFArray) })
            if failure == "none" {
                do { try ExportSaveDestination.validate(panel: panel, request: current, reader: reader) }
                catch { throw TestFailure(description: "A complete native Save destination fixture was rejected: \(error)") }
                healthyReader = reader
            } else {
                try rejects({ try ExportSaveDestination.validate(panel: panel, request: current, reader: reader) }, "Save destination accepted unqualified evidence: \(failure)")
            }
            try expect(fixtureError == nil, "Save destination fixture mutation failed: \(failure): \(String(describing: fixtureError))")
            try FileManager.default.removeItem(at: job)
            if FileManager.default.fileExists(atPath: parked.path) { try FileManager.default.removeItem(at: parked) }
        }
        // A new job must not inherit another job's valid directory URL, even when its filename matches.
        let isolated = LiveExportRequest(schema: current.schema, action: current.action, live_pid: current.live_pid,
            expected_window_title: current.expected_window_title, output_path: other.appendingPathComponent("kenn-analysis.wav").path,
            render_start: current.render_start, render_length: current.render_length, sample_rate: current.sample_rate, timeout_seconds: current.timeout_seconds)
        try isolated.validate()
        try FileManager.default.createDirectory(at: job, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        try rejects({ try ExportSaveDestination.validate(panel: panel, request: isolated, reader: healthyReader!) }, "Another job reused the previous Save destination")
        do { try ExportSaveDestination.validate(panel: panel, request: current, reader: healthyReader!) }
        catch { throw TestFailure(description: "A fresh destination read inherited another fixture's state: \(error)") }
        let remaining = try FileManager.default.contentsOfDirectory(atPath: job.path)
        try expect(remaining.isEmpty, "Read-only destination validation created a file")
        let cancelled = job.appendingPathComponent("cancel.requested")
        try Data().write(to: cancelled)
        var touchedAX = false
        let unread = ExportAXReader(deadline: .distantFuture, copyValue: { _, _ in
            touchedAX = true
            return (.cannotComplete, nil)
        })
        try rejects({ try ExportSaveDestination.validate(panel: panel, request: current, reader: unread) }, "A pre-existing cancellation marker was accepted")
        try expect(!touchedAX, "A cancelled destination read queried the Save panel")
        try FileManager.default.removeItem(at: job)
        print("PASS: read-only Save destination profile, URL/directory identity, cancellation, races and isolated validation")
    }

    private static func cancellationAfterMenuClosesOnlyTheNewExportDialog(_ request: LiveExportRequest) throws {
        let main = AXUIElementCreateApplication(Int32.max - 100)
        let dialog = AXUIElementCreateApplication(Int32.max - 101)
        let menuBar = AXUIElementCreateApplication(Int32.max - 102)
        let file = AXUIElementCreateApplication(Int32.max - 103)
        let menu = AXUIElementCreateApplication(Int32.max - 104)
        let export = AXUIElementCreateApplication(Int32.max - 105)
        let cancel = AXUIElementCreateApplication(Int32.max - 106)
        let marker = URL(fileURLWithPath: request.output_path).deletingLastPathComponent().appendingPathComponent("cancel.requested")
        var visible = false
        var cancelPresses = 0
        var fixtureError: Error?
        defer { try? FileManager.default.removeItem(at: marker) } // This fixture owns the generated cancellation marker.
        func children(_ node: AXUIElement) -> [AXUIElement] {
            if CFEqual(node, menuBar) { return [file] }
            if CFEqual(node, file) { return [menu] }
            if CFEqual(node, menu) { return [export] }
            if CFEqual(node, dialog) { return [cancel] }
            return [] // All other controls are leaves in this complete fake tree.
        }
        let environment = LiveExportEnvironment(trusted: { true }, isLive: { _ in true }, reader: { deadline in
            ExportAXReader(deadline: deadline, copyValue: { node, key in
                if key == kAXMenuBarAttribute { return (.success, menuBar) }
                if key == kAXTitleAttribute {
                    if CFEqual(node, main) { return (.success, request.expected_window_title as CFString) }
                    if CFEqual(node, dialog) { return (.success, "Export Audio/Video" as CFString) }
                    if CFEqual(node, file) { return (.success, "File" as CFString) }
                    if CFEqual(node, export) { return (.success, "Export Audio/Video…" as CFString) }
                }
                if key == kAXRoleAttribute {
                    return (.success, (CFEqual(node, main) || CFEqual(node, dialog) ? kAXWindowRole : (CFEqual(node, cancel) ? kAXButtonRole : kAXMenuRole)) as CFString)
                }
                if key == kAXSubroleAttribute {
                    return (.success, (CFEqual(node, dialog) ? kAXDialogSubrole : kAXStandardWindowSubrole) as CFString)
                }
                if key == kAXIdentifierAttribute, CFEqual(node, cancel) { return (.success, "Base.FinalButtonsBox.CancelButton" as CFString) }
                if key == kAXEnabledAttribute, CFEqual(node, cancel) { return (.success, kCFBooleanTrue) }
                return (.noValue, nil) // Optional attributes do not contribute to this ownership fixture.
            }, countValues: { node, key in
                (.success, key == kAXWindowsAttribute ? (visible ? 2 : 1) : children(node).count)
            }, copyValues: { node, key, _ in
                (.success, (key == kAXWindowsAttribute ? (visible ? [main, dialog] : [main]) : children(node)) as CFArray)
            })
        }, press: { node in
            if CFEqual(node, export) {
                visible = true
                do { try Data().write(to: marker) } catch { fixtureError = error }
                return .success
            }
            if CFEqual(node, cancel) { cancelPresses += 1; visible = false; return .success }
            return .failure // A different action must never be attempted by this fixture.
        })
        let receipt = LiveExportAccessibility(request, environment: environment).run(supervised: true, enabled: true)
        try expect(fixtureError == nil, "The post-menu cancellation fixture could not create its marker")
        // The old loop checked cancellation before acquiring the dialog and left it open with no cleanup attempt.
        try expect(cancelPresses == 1 && !visible, "Cancellation after the menu press left the newly opened export dialog visible")
        try expect(receipt.status == "cancelled" && receipt.owned_dialog && receipt.cleanup_error == nil && !receipt.writer_closed,
                   "Post-menu cancellation lost its owned-dialog or fail-closed writer evidence")
    }

    private static func actualCallerOwnsAndCancelsOnlyQualifiedTransitions(_ request: LiveExportRequest) throws {
        let scenarios = ["healthy", "cancel-profile", "deadline-profile", "never-appears", "cancel-never-appears", "cancel-delayed",
                         "deadline-acquisition", "existing-dialog", "foreign-dialog", "ambiguous-dialog", "replaced-main", "extra-window",
                         "duplicate-windows", "process-before-menu", "trust-before-menu", "broken-marker-before-menu", "missing-cancel",
                         "cleanup-replaced-dialog", "cleanup-process", "cleanup-trust", "cleanup-main", "cleanup-extra-dialog",
                         "cleanup-replaced-cancel", "cleanup-disabled", "cleanup-role", "cleanup-identifier", "cleanup-boolean",
                         "cleanup-read-failed", "cancel-rejected", "cancel-stuck", "close-read-failed", "close-replacement",
                         "main-role", "main-role-absent", "main-subrole", "main-subrole-absent", "cleanup-extra-window",
                         "cleanup-last-trust", "cleanup-last-process", "cancel-late-acquisition"]
        for scenario in scenarios {
            let fixture = ExportCallerFixture(request: request, scenario: scenario)
            let caller = LiveExportAccessibility(request, environment: fixture.environment)
            let receipt = caller.run(supervised: true, enabled: true)
            try expect(fixture.error == nil, "Caller fixture mutation failed: \(scenario): \(String(describing: fixture.error))")
            try expect(!receipt.writer_closed && receipt.status != "completed" && fixture.otherPresses == 0,
                       "Caller claimed render completion or attempted an Export/Save action: \(scenario)")
            let beforeMenu = ["existing-dialog", "duplicate-windows", "process-before-menu", "trust-before-menu", "broken-marker-before-menu", "main-role", "main-role-absent", "main-subrole", "main-subrole-absent"].contains(scenario)
            let acquired = ["healthy", "cancel-profile", "deadline-profile", "cancel-delayed"].contains(scenario) || scenario.hasPrefix("cleanup-") || scenario.hasPrefix("close-") || ["cancel-rejected", "cancel-stuck"].contains(scenario)
            let cleanupBlocked = scenario.hasPrefix("cleanup-")
            try expect(fixture.menuPresses == (beforeMenu ? 0 : 1), "Unexpected export-menu action count: \(scenario)")
            try expect(receipt.owned_dialog == acquired, "Caller adopted an unqualified dialog or lost its acquired dialog: \(scenario)")
            try expect(fixture.cancelPresses == (acquired && !cleanupBlocked ? 1 : 0), "Caller pressed a foreign/stale Cancel control or omitted valid cleanup: \(scenario)")
            if acquired {
                let cleanupFailed = cleanupBlocked || ["cancel-rejected", "cancel-stuck", "close-read-failed", "close-replacement"].contains(scenario)
                try expect((receipt.cleanup_error != nil) == cleanupFailed, "Caller cleanup readback was misreported: \(scenario)")
                if !cleanupFailed { try expect(!fixture.visible, "Successful cleanup left its owned dialog visible: \(scenario)") }
            }
            if ["cancel-profile", "cancel-delayed", "broken-marker-before-menu"].contains(scenario) {
                try expect(receipt.status == "cancelled", "A current cancellation was lost: \(scenario)")
            }
            if ["cancel-never-appears", "cancel-late-acquisition"].contains(scenario) {
                try expect(receipt.error_code == "cancel_acquisition_unresolved" && receipt.status == "cancelled" && fixture.elapsed <= 2.01,
                           "Cancelled acquisition waited for the full request timeout or hid unresolved dialog state")
            }
            if scenario == "never-appears" { try expect(fixture.elapsed <= 10.01, "Acquisition polling exceeded its request acceptance budget") }
            if scenario == "cancel-stuck" { try expect(fixture.elapsed <= 2.01 && fixture.sleeps <= 41, "Cleanup polling exceeded its two-second acceptance budget") }
            if scenario == "deadline-profile" { try expect(receipt.error_code == "accessibility_deadline", "A late profile read was accepted") }
            if scenario == "healthy" {
                let presses = fixture.menuPresses + fixture.cancelPresses
                let reused = caller.run(supervised: true, enabled: true)
                try expect(reused.error_code == "request_already_used" && fixture.menuPresses + fixture.cancelPresses == presses,
                           "Reusing one caller discarded its prior ownership and performed another UI action")
            }
            fixture.removeMarker()
            try expect(fixture.error == nil, "Caller fixture marker cleanup failed: \(scenario): \(String(describing: fixture.error))")
        }
        // A fresh caller after clean cancellation has separate ownership state, rather than a sticky global dialog.
        for _ in 0..<2 {
            let fresh = ExportCallerFixture(request: request, scenario: "healthy")
            let receipt = LiveExportAccessibility(request, environment: fresh.environment).run(supervised: true, enabled: true)
            try expect(receipt.owned_dialog && receipt.cleanup_error == nil && fresh.cancelPresses == 1 && !fresh.visible,
                       "A fresh isolated caller inherited another invocation's ownership or failure")
        }
        print("PASS: \(scenarios.count) actual caller lifecycle scenarios, bounded cancellation/cleanup, reuse refusal and fresh-instance recovery")
    }

    private static func incompletePreflightNeverPressesExport(_ request: LiveExportRequest) throws {
        let window = AXUIElementCreateApplication(Int32.max)
        let menuBar = AXUIElementCreateApplication(Int32.max - 1)
        let file = AXUIElementCreateApplication(Int32.max - 2)
        let menu = AXUIElementCreateApplication(Int32.max - 3)
        let export = AXUIElementCreateApplication(Int32.max - 4)
        for failure in ["none", "windows", "dialogs", "children", "role", "overflow", "malformed", "deadline"] {
            var windowCounts = 0
            var presses = 0
            func children(_ node: AXUIElement) -> [AXUIElement] {
                if CFEqual(node, menuBar) { return [file] }
                if CFEqual(node, file) { return [menu] }
                if CFEqual(node, menu) { return [export] }
                return [] // All other fixture nodes are leaves; no native AX read is needed.
            }
            let environment = LiveExportEnvironment(trusted: { true }, isLive: { _ in true }, reader: { deadline in
                ExportAXReader(deadline: failure == "deadline" ? .distantPast : deadline, copyValue: { node, key in
                    if key == kAXMenuBarAttribute { return (.success, menuBar) }
                    if key == kAXTitleAttribute {
                        if CFEqual(node, window) { return (.success, request.expected_window_title as CFString) }
                        if CFEqual(node, file) { return (.success, "File" as CFString) }
                        if CFEqual(node, export) { return (.success, "Export Audio/Video…" as CFString) }
                    }
                    if key == kAXRoleAttribute { return failure == "role" ? (.cannotComplete, nil) : (.success, kAXWindowRole as CFString) }
                    if key == kAXSubroleAttribute { return (.success, kAXStandardWindowSubrole as CFString) }
                    return (.noValue, nil) // Optional titles/identifiers are explicitly absent in this fixture.
                }, countValues: { node, key in
                    if key == kAXWindowsAttribute {
                        windowCounts += 1
                        if failure == "windows" || (failure == "dialogs" && windowCounts > 2) { return (.cannotComplete, 0) }
                        return (.success, 1)
                    }
                    if CFEqual(node, window) {
                        if failure == "children" { return (.cannotComplete, 0) }
                        if failure == "overflow" { return (.success, ExportAXReader.maximumNodes + 1) }
                    }
                    return (.success, children(node).count)
                }, copyValues: { node, key, _ in
                    if key == kAXWindowsAttribute {
                        return (.success, failure == "malformed" ? [NSNumber(value: 1)] as CFArray : [window] as CFArray)
                    }
                    return (.success, children(node) as CFArray)
                })
            }, press: { _ in
                presses += 1
                return .failure // Positive control reaches the action seam but never opens a real dialog.
            })
            let receipt = LiveExportAccessibility(request, environment: environment).run(supervised: true, enabled: true)
            if failure == "none" {
                try expect(presses == 1 && receipt.error_code == "export_menu_rejected", "The action spy never reached a valid menu preflight")
            } else {
                // Caller coverage matters: a rejecting reader must stop the actual AXPress path.
                try expect(presses == 0 && receipt.status == "unavailable", "Incomplete preflight pressed Export: \(failure)")
            }
            try expect(!receipt.writer_closed && !receipt.owned_dialog, "A preflight failure claimed an owned dialog or closed writer")
        }
        print("PASS: actual export orchestration performs zero presses after incomplete preflight")
    }

    private static func wavAndDescriptorEvidenceShareOneGeneration(output: URL, root: URL) throws {
        try wav().write(to: output)
        let first = try ExportWAV.validate(output.path)
        let replacement = root.appendingPathComponent("replacement.wav")
        try wav().write(to: replacement)
        guard rename(replacement.path, output.path) == 0 else { throw TestFailure(description: "Fixture replacement failed") }
        // The previous path-only descriptor scan accepted B using validation of A.
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: first) == nil, "A replaced WAV reused another file's validation evidence")
        let second = try ExportWAV.validate(output.path)
        for mask in 0..<16 {
            let evidence = ExportCompletionEvidence(observedExportProgress: mask & 1 != 0, exportDialogsGone: mask & 2 != 0,
                validWAV: mask & 4 != 0 ? second : nil,
                writer: ExportDescriptorEvidence(identity: second, hasNoOpenDescriptor: mask & 8 != 0))
            try expect(evidence.permitsPublication == (mask == 15), "Incomplete export evidence allowed publication")
        }
        try expect(!ExportCompletionEvidence(observedExportProgress: true, exportDialogsGone: true, validWAV: second, writer: nil).permitsPublication, "Unknown inspection was treated as writer closure")
        try expect(!ExportCompletionEvidence(observedExportProgress: true, exportDialogsGone: true, validWAV: first,
            writer: ExportDescriptorEvidence(identity: second, hasNoOpenDescriptor: true)).permitsPublication, "Completion combined two different WAV generations")
        try expect(inspectLiveOutputDescriptors(pid: Int32.max, outputPath: output.path, expected: second) == nil, "A missing process was treated as proven closed")
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: second, inspect: { _, _ in nil }) == nil, "A failed descriptor inspection was treated as closed")

        let writer = try FileHandle(forWritingTo: output)
        try writer.seek(toOffset: 44) // Change PCM only, keeping format and file length valid.
        try writer.write(contentsOf: Data([1, 0, 0, 0, 0, 0]))
        try writer.close()
        // Pin an explicitly different mtime so this boundary never relies on waiting for a clock tick.
        var times = [timespec(tv_sec: 0, tv_nsec: Int(UTIME_OMIT)), timespec(tv_sec: second.modifiedSeconds - 1, tv_nsec: second.modifiedNanoseconds)]
        guard utimensat(AT_FDCWD, output.path, &times, AT_SYMLINK_NOFOLLOW) == 0 else { throw TestFailure(description: "Fixture timestamp update failed") }
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: second) == nil, "A same-size in-place WAV rewrite reused stale validation")
        times[1] = timespec(tv_sec: second.modifiedSeconds, tv_nsec: second.modifiedNanoseconds)
        guard utimensat(AT_FDCWD, output.path, &times, AT_SYMLINK_NOFOLLOW) == 0 else { throw TestFailure(description: "Fixture timestamp restore failed") }
        let restored = ExportFileIdentity.at(output.path)!
        try expect(restored.modifiedSeconds == second.modifiedSeconds && restored.modifiedNanoseconds == second.modifiedNanoseconds, "Fixture did not restore mtime")
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: second) == nil, "Restored mtime hid the WAV's changed ctime")

        let beforeScan = try ExportWAV.validate(output.path)
        let raced = inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: beforeScan, inspect: { _, _ in
            do {
                try wav().write(to: replacement)
                guard rename(replacement.path, output.path) == 0 else { return nil } // A failed fixture mutation cannot prove closure.
            } catch { return nil } // Failed fixture I/O must fail the assertion rather than report success.
            return true
        })
        try expect(raced == nil, "A WAV replaced during descriptor inspection was accepted")
        let beforeLink = try ExportWAV.validate(output.path)
        try FileManager.default.linkItem(at: output, to: replacement)
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: beforeLink) == nil, "A new hard link preserved completion evidence")
        try FileManager.default.removeItem(at: replacement)
        let beforeRemoval = try ExportWAV.validate(output.path)
        try FileManager.default.removeItem(at: output)
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: beforeRemoval) == nil, "A missing WAV retained completion evidence")
        try FileManager.default.createSymbolicLink(at: output, withDestinationURL: URL(fileURLWithPath: "/dev/null"))
        try expect(inspectLiveOutputDescriptors(pid: getpid(), outputPath: output.path, expected: beforeRemoval) == nil, "A symbolic-link replacement retained completion evidence")
        try FileManager.default.removeItem(at: output)

        for replacePath in [true, false] {
            try wav().write(to: output)
            var mutated = false
            // Inject only the read boundary; the production parser still opens, parses and restats real fixture files.
            try rejects({ _ = try ExportWAV.validate(output.path, readBytes: { file, count in
                let bytes = try file.read(upToCount: count) ?? Data()
                if !mutated {
                    mutated = true
                    if replacePath {
                        try wav().write(to: replacement)
                        guard rename(replacement.path, output.path) == 0 else { throw TestFailure(description: "Fixture rename during parse failed") }
                    } else {
                        let changed = try FileHandle(forWritingTo: output)
                        try changed.seek(toOffset: 44)
                        try changed.write(contentsOf: Data([2, 0, 0, 0, 0, 0]))
                        try changed.close()
                    }
                }
                return bytes
            }) }, "A WAV changed during header parsing was validated")
        }
        print("PASS: WAV generation binding, replacement/rewrite/link races, parser rechecks and completion identity")
    }

    private static func axReadsRejectFailuresAndTruncation() throws {
        let root = AXUIElementCreateApplication(Int32.max)
        let child = AXUIElementCreateApplication(Int32.max - 1)
        let hidden = AXUIElementCreateApplication(Int32.max - 2)
        for error in [AXError.cannotComplete, .invalidUIElement, .failure, .notImplemented, .illegalArgument] {
            let failed = ExportAXReader(deadline: .distantFuture,
                copyValue: { _, _ in (error, nil) }, countValues: { _, _ in (error, 0) })
            // Failed reads used to look like no windows or children, permitting an unsafe Export action.
            try rejects({ _ = try failed.elements(root, kAXWindowsAttribute) }, "A failed AX window read was treated as an empty list")
            try rejects({ _ = try failed.elements(root, kAXChildrenAttribute, allowAbsent: true) }, "A failed AX child read was treated as a leaf")
            try rejects({ _ = try failed.value(root, kAXIdentifierAttribute) }, "A failed optional AX read was treated as absence")
        }
        for absent in [AXError.noValue, .attributeUnsupported] {
            let reader = ExportAXReader(deadline: .distantFuture,
                copyValue: { _, _ in (absent, nil) }, countValues: { _, _ in (absent, 0) })
            let optional = try reader.value(root, kAXIdentifierAttribute)
            let leaf = try reader.elements(root, kAXChildrenAttribute, allowAbsent: true)
            try expect(optional == nil && leaf.isEmpty, "Explicit optional absence did not produce an empty leaf")
            try rejects({ _ = try reader.value(root, kAXRoleAttribute, required: true) }, "A required role was allowed to disappear")
            try rejects({ _ = try reader.elements(root, kAXWindowsAttribute) }, "Missing required AXWindows was treated as empty")
        }
        let nilValue = ExportAXReader(deadline: .distantFuture, copyValue: { _, _ in (.success, nil) })
        try rejects({ _ = try nilValue.value(root, kAXValueAttribute) }, "A successful but nil AX result was accepted")
        let wrongText = ExportAXReader(deadline: .distantFuture, copyValue: { _, _ in (.success, NSNumber(value: 1)) })
        try rejects({ _ = try wrongText.string(root, kAXTitleAttribute) }, "A malformed title became missing text")

        var copied = false
        let oversized = ExportAXReader(deadline: .distantFuture,
            countValues: { _, _ in (.success, ExportAXReader.maximumNodes + 1) },
            copyValues: { _, _, _ in copied = true; return (.success, [child] as CFArray) })
        try rejects({ _ = try oversized.elements(root, kAXChildrenAttribute) }, "An over-limit AX array was accepted")
        try expect(!copied, "An oversized AX array was allocated before checking its count")
        for bad in [nil, NSNumber(value: 1), [NSNumber(value: 1)] as CFArray, [child, hidden] as CFArray] as [CFTypeRef?] {
            let malformed = ExportAXReader(deadline: .distantFuture,
                countValues: { _, _ in (.success, 1) }, copyValues: { _, _, maximum in
                    copied = maximum == 2 // Count plus one observes growth instead of silently truncating it.
                    return (.success, bad)
                })
            try rejects({ _ = try malformed.elements(root, kAXChildrenAttribute) }, "A malformed or growing AX array was accepted")
            try expect(copied, "The AX copy did not request one bounded growth-detection slot")
        }
        var countCalls = 0
        let changing = ExportAXReader(deadline: .distantFuture, countValues: { _, _ in
            countCalls += 1
            return (.success, countCalls == 1 ? 1 : 2)
        }, copyValues: { _, _, _ in (.success, [child] as CFArray) })
        try rejects({ _ = try changing.elements(root, kAXWindowsAttribute) }, "An AX list changed during enumeration without rejection")
        let failedCopy = ExportAXReader(deadline: .distantFuture,
            countValues: { _, _ in (.success, 1) }, copyValues: { _, _, _ in (.cannotComplete, nil) })
        try rejects({ _ = try failedCopy.elements(root, kAXWindowsAttribute) }, "A failed bounded AX copy was accepted")

        var hasHiddenChild = true
        let tree = ExportAXReader(deadline: .distantFuture, countValues: { node, _ in
            (.success, CFEqual(node, root) || (CFEqual(node, child) && hasHiddenChild) ? 1 : 0)
        }, copyValues: { node, _, _ in (.success, [CFEqual(node, root) ? child : hidden] as CFArray) })
        // The old prefix traversal hid a third node that could contain another dialog or duplicate control.
        try rejects({ _ = try tree.nodes(roots: [root], limit: 2) }, "An overflowing AX tree was silently truncated")
        hasHiddenChild = false
        let complete = try tree.nodes(roots: [root], limit: 2)
        try expect(complete.count == 2, "An exactly bounded complete tree was rejected")
        try rejects({ _ = try tree.nodes(roots: [root, child, hidden], limit: 2) }, "Multiple roots bypassed the shared tree budget")

        let start = Date(timeIntervalSince1970: 1)
        var clock = start
        let late = ExportAXReader(deadline: start.addingTimeInterval(1), now: { clock }, copyValue: { _, _ in
            clock = start.addingTimeInterval(2)
            return (.success, "late" as CFString)
        }, countValues: { _, _ in
            clock = start.addingTimeInterval(2)
            return (.success, 0)
        })
        try rejects({ _ = try late.value(root, kAXTitleAttribute) }, "An AX value returned after the deadline was accepted")
        clock = start
        try rejects({ _ = try late.elements(root, kAXWindowsAttribute) }, "An AX count returned after the deadline was accepted")
        let healthy = ExportAXReader(deadline: .distantFuture, countValues: { _, _ in (.success, 0) })
        let empty = try healthy.nodes(roots: [root])
        try expect(empty.count == 1, "Another reader's timeout contaminated a fresh tree")
        print("PASS: AX failure/absence separation, bounded arrays and complete trees, deadlines and reader isolation")
    }

    private static func wav(sampleRate: UInt32 = 48_000, channels: UInt16 = 2, frames: UInt32 = 1) -> Data {
        var bytes = Data()
        func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
        func u16(_ value: UInt16) { bytes.append(UInt8(value & 255)); bytes.append(UInt8(value >> 8)) }
        func u32(_ value: UInt32) { for shift in stride(from: 0, to: 32, by: 8) { bytes.append(UInt8((value >> shift) & 255)) } }
        text("RIFF"); u32(36 + frames * 6); text("WAVEfmt "); u32(16)
        u16(1); u16(channels); u32(sampleRate); u32(sampleRate * 6); u16(6); u16(24)
        text("data"); u32(frames * 6); bytes.append(contentsOf: [0, 0, 0, 0, 0, 0])
        return bytes
    }
}
