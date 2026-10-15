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
        let root = URL(fileURLWithPath: canonicalPath(FileManager.default.temporaryDirectory.path)!).appendingPathComponent("kenn-export-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) } // Tests remove only their exclusive generated fixture directory.
        func request(path: String? = nil, action: String = "export", sampleRate: Int = 48_000, start: String = "1.1.1", length: String = "32.0.0") -> LiveExportRequest {
            LiveExportRequest(schema: "kenn.live_export_request.v1", action: action, live_pid: getpid(), expected_window_title: "Disposable Test Set", output_path: path ?? root.appendingPathComponent("kenn-analysis.wav").path, render_start: start, render_length: length, sample_rate: sampleRate, timeout_seconds: 10)
        }
        let original = request()
        try original.validate()
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

        for mask in 0..<16 {
            let evidence = ExportCompletionEvidence(observedExportProgress: mask & 1 != 0, exportDialogsGone: mask & 2 != 0, validWAV: mask & 4 != 0, liveHasNoOpenOutputDescriptor: mask & 8 != 0)
            try expect(evidence.permitsPublication == (mask == 15), "Incomplete export evidence allowed publication")
        }
        try expect(!ExportCompletionEvidence(observedExportProgress: true, exportDialogsGone: true, validWAV: true, liveHasNoOpenOutputDescriptor: nil).permitsPublication, "Permission failure was treated as writer closure")
        try expect(liveHasNoOpenOutputDescriptor(pid: Int32.max, outputPath: original.output_path) == nil, "A missing writer process was treated as proven closed")

        let valid = wav()
        try valid.write(to: output)
        try ExportWAV.validate(output.path)
        let alias = root.appendingPathComponent("linked-output.wav")
        try FileManager.default.linkItem(at: output, to: alias)
        try rejects({ try ExportWAV.validate(output.path) }, "A hard-linked WAV was accepted as exclusively owned")
        try FileManager.default.removeItem(at: alias)
        let handle = try FileHandle(forWritingTo: output)
        try expect(liveHasNoOpenOutputDescriptor(pid: getpid(), outputPath: output.path) == false, "An open writer descriptor was missed")
        try handle.close()
        try expect(liveHasNoOpenOutputDescriptor(pid: getpid(), outputPath: output.path) == true, "The closed self-process descriptor could not be verified")
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
