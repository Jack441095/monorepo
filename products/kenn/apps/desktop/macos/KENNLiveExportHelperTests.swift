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
