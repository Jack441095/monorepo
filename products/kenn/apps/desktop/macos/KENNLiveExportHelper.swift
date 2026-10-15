import AppKit
import ApplicationServices
import Darwin
import Foundation

/// A single bounded request. The caller owns a fresh private job directory and all cleanup.
struct LiveExportRequest: Codable {
    let schema: String
    let action: String
    let live_pid: Int32
    let expected_window_title: String
    let output_path: String
    let render_start: String
    let render_length: String
    let sample_rate: Int
    let timeout_seconds: Int

    func validate() throws {
        guard schema == "kenn.live_export_request.v1", ["inspect", "export"].contains(action), live_pid > 0 else {
            throw ExportProblem.invalid("Invalid request schema, action or process identifier.")
        }
        guard !expected_window_title.isEmpty, expected_window_title.utf8.count <= 512,
              !expected_window_title.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
            throw ExportProblem.invalid("An exact, bounded Live window title is required.")
        }
        guard sample_rate == 48_000, (1...600).contains(timeout_seconds),
              Self.validPosition(render_start, start: true), Self.validPosition(render_length, start: false) else {
            throw ExportProblem.invalid("Use 48000 Hz, a 1–600 second timeout and explicit bars.beats.sixteenths range values.")
        }
        let output = URL(fileURLWithPath: output_path)
        let parent = output.deletingLastPathComponent()
        guard output_path.hasPrefix("/"), output.lastPathComponent == "kenn-analysis.wav",
              output.standardizedFileURL.path == output_path,
              canonicalPath(parent.path) == parent.path else {
            throw ExportProblem.invalid("The output must be a canonical absolute job path ending in kenn-analysis.wav.")
        }
        var info = stat()
        guard lstat(parent.path, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
              info.st_uid == getuid(), info.st_mode & 0o777 == 0o700 else {
            throw ExportProblem.invalid("The job directory must already exist, belong to this user and have mode 0700.")
        }
        guard lstat(output_path, &info) != 0, errno == ENOENT else {
            throw ExportProblem.invalid("The helper never overwrites an existing file or symbolic link.")
        }
        let entries = try FileManager.default.contentsOfDirectory(atPath: parent.path)
        guard entries.allSatisfy({ ["manifest.json", "receipt.json", "cancel.requested"].contains($0) }) else {
            throw ExportProblem.invalid("The job directory may contain only its ownership manifest, receipt and cancellation marker.")
        }
        for entry in entries {
            let path = parent.appendingPathComponent(entry).path
            guard lstat(path, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
                  info.st_uid == getuid(), info.st_nlink == 1, info.st_size <= 65_536 else {
                throw ExportProblem.invalid("Job metadata must be owned regular files of at most 64 KiB each.")
            }
        }
    }

    private static func validPosition(_ text: String, start: Bool) -> Bool {
        let parts = text.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, parts.allSatisfy({ !$0.isEmpty && $0.count <= 6 && $0.allSatisfy(\.isNumber) }),
              let bars = Int(parts[0]), let beats = Int(parts[1]), let subdivisions = Int(parts[2]) else {
            // Ambiguous or locale-specific values cannot bind the requested arrangement range.
            return false
        }
        return start ? bars > 0 : bars + beats + subdivisions > 0
    }
}

struct LiveExportReceipt: Encodable {
    let schema = "kenn.live_export_receipt.v1"
    var status: String
    var writer_closed = false
    let output_path: String
    let live_pid: Int32
    let render_start: String
    let render_length: String
    let sample_rate: Int
    let channels = 2
    var error_code: String?
    var error: String?
    var owned_dialog = false
    var cleanup_error: String?

    init(_ request: LiveExportRequest, problem: ExportProblem) {
        status = problem.status
        output_path = request.output_path
        live_pid = request.live_pid
        render_start = request.render_start
        render_length = request.render_length
        sample_rate = request.sample_rate
        error_code = problem.code
        error = problem.message
    }
}

struct ExportProblem: Error {
    let status: String
    let code: String
    let message: String

    static func invalid(_ message: String) -> Self {
        Self(status: "failed", code: "invalid_request", message: message)
    }
    static func unavailable(_ code: String, _ message: String) -> Self {
        Self(status: "unavailable", code: code, message: message)
    }
}

/// Matches the read-only Live 12 AX identifiers observed during the supervised 15 Oct 2026 probe.
enum LiveExportProfile {
    static let fixedSettings = [
        "Base.RenderedTrack": "Main",
        "Base.RenderAsLoopBox.RenderAsLoop": "Off",
        "Base.ConvertToMonoBox.ConvertToMono": "Off",
        "Base.NormalizeBox.Normalize": "Off",
        "Base.AnalysisFileBox.CreateAnalysisFile": "Off",
        "Base.SampleRateBox.SampleRate": "48000",
        "Base.EncodePcmBox.EncodePcm": "On",
        "Base.FileTypeBox.FileType": "WAV",
        "Base.FileTypeOptionsBox.FileTypeOptionsCardView.BitDepthBox.BitDepth": "24",
        "Base.EncodeMp3Box.EncodeMp3": "Off",
        "Base.VideoOptionsCardView.CreateVideoBox.CreateVideo": "Off",
    ]

    static func validate(values: [String: [String]], request: LiveExportRequest) throws {
        var expected = fixedSettings
        for (prefix, position) in [("Base.RenderStartBox.RenderStart", request.render_start),
                                   ("Base.RenderLengthBox.RenderLength", request.render_length)] {
            for (component, number) in zip(["Bars", "Beats", "Subdivisions"], position.split(separator: ".")) {
                expected["\(prefix).\(component)"] = String(Int(number)!)
            }
        }
        for identifier in expected.keys.sorted() {
            guard let matches = values[identifier], matches.count == 1 else {
                throw ExportProblem.unavailable("export_control_unqualified", "A required export setting is inaccessible or ambiguous: \(identifier).")
            }
            guard matches[0] == expected[identifier] else {
                // We inspect existing preferences; changing them needs a separately qualified restoration contract.
                throw ExportProblem.unavailable("export_settings_mismatch", "The existing export setting does not match the scan profile: \(identifier).")
            }
        }
    }
}

/// Completion needs independent writer evidence; a disappearing dialog alone is insufficient.
struct ExportCompletionEvidence {
    let observedExportProgress: Bool
    let exportDialogsGone: Bool
    let validWAV: Bool
    let liveHasNoOpenOutputDescriptor: Bool?

    var permitsPublication: Bool {
        observedExportProgress && exportDialogsGone && validWAV && liveHasNoOpenOutputDescriptor == true
    }
}

/// Checks the exact PCM format without loading an entire arrangement into memory.
enum ExportWAV {
    static let maximumBytes: UInt64 = 150 * 1_024 * 1_024 // 150 MiB matches the existing offline upload ceiling.

    static func validate(_ path: String) throws {
        var info = stat()
        guard lstat(path, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
              info.st_size >= 44, UInt64(info.st_size) <= maximumBytes else {
            throw ExportProblem.invalid("The completed WAV must be a regular file within the 150 MiB limit.")
        }
        let descriptor = open(path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw ExportProblem.invalid("The WAV could not be opened without following a symbolic link.") }
        let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? file.close() } // Validation owns only its read handle, never Live's writer.
        var opened = stat()
        guard fstat(descriptor, &opened) == 0, opened.st_dev == info.st_dev, opened.st_ino == info.st_ino,
              opened.st_size == info.st_size else {
            throw ExportProblem.invalid("The WAV identity changed during validation.")
        }
        func read(_ count: Int) throws -> Data {
            let bytes = try file.read(upToCount: count) ?? Data()
            guard bytes.count == count else { throw ExportProblem.invalid("The WAV is truncated.") }
            return bytes
        }
        let header = try read(12)
        guard String(data: header.prefix(4), encoding: .ascii) == "RIFF",
              String(data: header.suffix(4), encoding: .ascii) == "WAVE",
              UInt64(u32(header, 4)) + 8 == UInt64(info.st_size) else {
            throw ExportProblem.invalid("A finalized RIFF/WAVE header is required; RF64 is not qualified.")
        }
        var validFormat = false
        var dataBytes: UInt64 = 0
        var offset: UInt64 = 12 // RIFF's identifier, length and WAVE identifier occupy 12 bytes.
        while offset + 8 <= UInt64(info.st_size) {
            try file.seek(toOffset: offset)
            let chunk = try read(8)
            let length = UInt64(u32(chunk, 4))
            let payload = offset + 8
            guard payload + length <= UInt64(info.st_size) else { throw ExportProblem.invalid("The WAV chunk extends beyond the file.") }
            let name = String(data: chunk.prefix(4), encoding: .ascii)
            if name == "fmt " {
                guard !validFormat, length == 16 else { throw ExportProblem.invalid("Only one 16-byte PCM format chunk is qualified.") }
                let format = try read(16)
                validFormat = u16(format, 0) == 1 && u16(format, 2) == 2 && u32(format, 4) == 48_000
                    && u32(format, 8) == 288_000 && u16(format, 12) == 6 && u16(format, 14) == 24
                // Stereo 24-bit PCM has six bytes per frame and 288000 bytes per second at 48 kHz.
                guard validFormat else { throw ExportProblem.invalid("The WAV must be stereo 48000 Hz, 24-bit PCM.") }
            } else if name == "data" {
                guard dataBytes == 0, length > 0, length % 6 == 0 else { throw ExportProblem.invalid("One nonempty, frame-aligned audio chunk is required.") }
                dataBytes = length
            }
            offset = payload + length + length % 2 // RIFF chunks use even-byte padding.
        }
        guard validFormat, dataBytes > 0, offset == UInt64(info.st_size) else {
            throw ExportProblem.invalid("The WAV has incomplete format, audio or trailing chunk data.")
        }
    }

    private static func u16(_ data: Data, _ offset: Int) -> UInt16 {
        UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
    }
    private static func u32(_ data: Data, _ offset: Int) -> UInt32 {
        UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 | UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
    }
}

func canonicalPath(_ path: String) -> String? {
    guard let resolved = realpath(path, nil) else { return nil } // Missing paths cannot establish a canonical parent.
    defer { free(resolved) }
    return String(cString: resolved)
}

/// Returns nil when macOS refuses inspection; lack of access never proves a writer closed.
func liveHasNoOpenOutputDescriptor(pid: Int32, outputPath: String) -> Bool? {
    var output = stat()
    guard lstat(outputPath, &output) == 0, output.st_mode & S_IFMT == S_IFREG else { return nil }
    let entrySize = MemoryLayout<proc_fdinfo>.stride
    let needed = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, nil, 0)
    guard needed > 0, needed <= 16_384 * entrySize else { return nil } // Bound the process snapshot to 16384 descriptors.
    var entries = [proc_fdinfo](repeating: proc_fdinfo(), count: Int(needed) / entrySize + 32)
    let capacity = entries.count * entrySize // Headroom detects descriptor growth without an unbounded retry loop.
    let actual = entries.withUnsafeMutableBytes { proc_pidinfo(pid, PROC_PIDLISTFDS, 0, $0.baseAddress, Int32(capacity)) }
    guard actual > 0, actual < capacity, Int(actual) % entrySize == 0 else { return nil }
    for entry in entries.prefix(Int(actual) / entrySize) where entry.proc_fdtype == PROX_FDTYPE_VNODE {
        var vnode = vnode_fdinfowithpath()
        let bytes = proc_pidfdinfo(pid, entry.proc_fd, PROC_PIDFDVNODEPATHINFO, &vnode, Int32(MemoryLayout.size(ofValue: vnode)))
        guard bytes == MemoryLayout.size(ofValue: vnode) else { return nil } // A racing or inaccessible descriptor leaves closure unproven.
        // Device/inode identity also catches macOS's /var versus /private/var aliases and hard links.
        let identity = vnode.pvip.vip_vi.vi_stat
        if identity.vst_dev == output.st_dev && identity.vst_ino == output.st_ino { return false }
    }
    return true
}

/// Restricts AX actions to a verified Ableton process and the one dialog this invocation opens.
final class LiveExportAccessibility {
    private let request: LiveExportRequest
    private let app: AXUIElement
    private var openedDialog: AXUIElement?
    private var ownedCancel: AXUIElement?
    private let deadline: Date

    init(_ request: LiveExportRequest) {
        self.request = request
        app = AXUIElementCreateApplication(request.live_pid)
        deadline = Date().addingTimeInterval(Double(request.timeout_seconds))
        AXUIElementSetMessagingTimeout(app, 2) // Two seconds bounds an unresponsive Live AX request.
    }

    func run(supervised: Bool, enabled: Bool) -> LiveExportReceipt {
        var receipt = LiveExportReceipt(request, problem: .unavailable("export_profile_unqualified", "Live's export range, settings and destination AX controls require supervised qualification."))
        do {
            try request.validate()
            guard request.action == "inspect" || (supervised && enabled) else {
                throw ExportProblem.unavailable("experimental_export_disabled", "Export requires KENN_EXPERIMENTAL_LIVE_EXPORT=1 and --supervised-test; production export is disabled.")
            }
            guard AXIsProcessTrusted() else {
                throw ExportProblem.unavailable("accessibility_not_granted", "Accessibility access is unavailable; this helper does not request or change permissions.")
            }
            try verifyLive()
            if request.action == "inspect" {
                // Inspection never opens a menu or a dialog, even when the experimental gate is enabled.
                return receipt
            }
            try checkCancellation()
            guard dialogs().isEmpty else {
                throw ExportProblem.unavailable("existing_dialog", "Close existing Live dialogs before a supervised export check.")
            }
            let menuBar = try element(app, kAXMenuBarAttribute)
            let file = try unique(children(menuBar), title: "File")
            let fileMenus = children(file)
            let exportItems = fileMenus.flatMap(children).filter { ["Export Audio/Video…", "Export Audio/Video..."].contains(title($0)) }
            guard exportItems.count == 1 else {
                throw ExportProblem.unavailable("export_menu_unavailable", "The fixed File > Export Audio/Video menu item is missing or ambiguous.")
            }
            guard AXUIElementPerformAction(exportItems[0], kAXPressAction as CFString) == .success else {
                throw ExportProblem.unavailable("export_menu_rejected", "Live did not accept the export menu action.")
            }
            while Date() < deadline {
                try checkCancellation()
                let candidates = dialogs().filter { title($0) == "Export Audio/Video" }
                if candidates.count == 1 {
                    guard windows().contains(where: { CFEqual($0, candidates[0]) }) else {
                        throw ExportProblem.unavailable("export_sheet_unqualified", "A sheet-based export dialog has no qualified cancellation readback.")
                    }
                    openedDialog = candidates[0]
                    let cancel = descendants(candidates[0]).filter {
                        (attribute($0, kAXIdentifierAttribute) as? String) == "Base.FinalButtonsBox.CancelButton"
                    }
                    if cancel.count == 1 { ownedCancel = cancel[0] }
                    receipt.owned_dialog = true
                    break
                }
                if candidates.count > 1 { throw ExportProblem.unavailable("ambiguous_export_dialog", "The export dialog cannot be identified uniquely.") }
                Thread.sleep(forTimeInterval: 0.1) // 100 ms polling stays off the audio callback and bounds cancellation latency.
            }
            guard openedDialog != nil else {
                throw ExportProblem.unavailable("export_dialog_unavailable", "Live did not expose an identifiable Export Audio/Video AX dialog before the deadline.")
            }
            if let dialog = openedDialog {
                var values: [String: [String]] = [:]
                for node in [dialog] + descendants(dialog) {
                    if let identifier = attribute(node, kAXIdentifierAttribute) as? String,
                       let value = attribute(node, kAXValueAttribute) {
                        let fixed = LiveExportProfile.fixedSettings[identifier]
                        if ["On", "Off"].contains(fixed), let number = value as? NSNumber, [0, 1].contains(number.intValue) {
                            values[identifier, default: []].append(number.intValue == 0 ? "Off" : "On")
                        } else {
                            values[identifier, default: []].append(String(describing: value))
                        }
                    }
                }
                try LiveExportProfile.validate(values: values, request: request)
            }
            // The read-only settings profile cannot qualify the save-panel destination or export lifecycle.
            // Do not press Export based on selected audio, guessed save controls or file-size stability.
            receipt.cleanup_error = cancelOwnedDialog()
            return receipt
        } catch let problem as ExportProblem {
            receipt = LiveExportReceipt(request, problem: problem)
        } catch {
            // Unexpected filesystem/AX errors fail closed; no arbitrary path or command is retried.
            receipt = LiveExportReceipt(request, problem: .unavailable("helper_error", "The bounded export inspection failed."))
        }
        receipt.owned_dialog = openedDialog != nil
        receipt.cleanup_error = cancelOwnedDialog()
        return receipt
    }

    private func verifyLive() throws {
        guard let running = NSRunningApplication(processIdentifier: request.live_pid),
              running.bundleIdentifier == "com.ableton.live",
              !running.isTerminated else {
            throw ExportProblem.unavailable("live_identity_mismatch", "The requested process is not a running Ableton Live application.")
        }
        let matches = windows().filter { title($0) == request.expected_window_title }
        guard matches.count == 1 else {
            throw ExportProblem.unavailable("window_identity_mismatch", "The exact expected Live window is missing or ambiguous.")
        }
    }

    private func checkCancellation() throws {
        let marker = URL(fileURLWithPath: request.output_path).deletingLastPathComponent().appendingPathComponent("cancel.requested")
        if FileManager.default.fileExists(atPath: marker.path) {
            throw ExportProblem(status: "cancelled", code: "cancel_requested", message: "The job owner requested cancellation.")
        }
    }

    private func cancelOwnedDialog() -> String? {
        guard let dialog = openedDialog else { return nil } // Never dismiss a dialog that predates this helper.
        // Retain only the exact button found before the request deadline, so timeout cleanup does not traverse a fresh UI.
        guard let cancel = ownedCancel, AXUIElementPerformAction(cancel, kAXPressAction as CFString) == .success else {
            return "The helper-owned export dialog could not be cancelled through its exact Cancel identifier."
        }
        let cancelDeadline = Date().addingTimeInterval(2) // Two seconds bounds cancellation readback after an expired request.
        while Date() < cancelDeadline {
            var current: CFTypeRef?
            let result = AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &current)
            if result == .success, let currentWindows = current as? [AXUIElement],
               !currentWindows.contains(where: { CFEqual($0, dialog) }) {
                // The qualified export dialog is a top-level AX window. A sheet profile needs separate readback.
                return nil
            }
            Thread.sleep(forTimeInterval: 0.05) // 50 ms checks observe cancellation without spinning.
        }
        return "The Cancel action was accepted but disappearance of the helper-owned dialog was not verified."
    }

    private func windows() -> [AXUIElement] { attribute(app, kAXWindowsAttribute) as? [AXUIElement] ?? [] }
    private func dialogs() -> [AXUIElement] {
        windows().flatMap { [$0] + descendants($0) }.filter { role($0) == kAXSheetRole || (attribute($0, kAXSubroleAttribute) as? String) == kAXDialogSubrole }
    }
    private func title(_ node: AXUIElement) -> String { attribute(node, kAXTitleAttribute) as? String ?? "" }
    private func role(_ node: AXUIElement) -> String { attribute(node, kAXRoleAttribute) as? String ?? "" }
    private func children(_ node: AXUIElement) -> [AXUIElement] { attribute(node, kAXChildrenAttribute) as? [AXUIElement] ?? [] }
    private func attribute(_ node: AXUIElement, _ key: String) -> CFTypeRef? {
        var value: CFTypeRef?
        guard Date() < deadline else { return nil } // Stop querying an unresponsive AX tree after the request deadline.
        guard AXUIElementCopyAttributeValue(node, key as CFString, &value) == .success else {
            // Missing/custom controls remain unknown, so callers reject the action instead of guessing.
            return nil
        }
        return value
    }
    private func element(_ node: AXUIElement, _ key: String) throws -> AXUIElement {
        guard let value = attribute(node, key), CFGetTypeID(value) == AXUIElementGetTypeID() else {
            throw ExportProblem.unavailable("inaccessible_menu", "Live did not expose the required native menu.")
        }
        return unsafeBitCast(value, to: AXUIElement.self)
    }
    private func unique(_ nodes: [AXUIElement], title expected: String) throws -> AXUIElement {
        let matches = nodes.filter { title($0) == expected }
        guard matches.count == 1 else { throw ExportProblem.unavailable("ambiguous_menu", "The fixed File menu is missing or ambiguous.") }
        return matches[0]
    }
    private func descendants(_ root: AXUIElement) -> [AXUIElement] {
        var queue = children(root)
        var result: [AXUIElement] = []
        while !queue.isEmpty, result.count < 2_048 { // At most 2048 nodes prevents pathological AX trees from retaining unbounded memory.
            let node = queue.removeFirst()
            result.append(node)
            if queue.count + result.count < 2_048 { queue.append(contentsOf: children(node).prefix(2_048 - queue.count - result.count)) }
        }
        return result
    }
}

#if !KENN_EXPORT_TESTS
@main
struct KENNLiveExportHelper {
    static func main() {
        do {
            let input = FileHandle.standardInput.readData(ofLength: 16_385) // Requests are capped at 16 KiB before JSON decoding.
            guard input.count <= 16_384 else { throw ExportProblem.invalid("The request exceeds 16 KiB.") }
            let request = try JSONDecoder().decode(LiveExportRequest.self, from: input)
            let receipt = LiveExportAccessibility(request).run(
                supervised: CommandLine.arguments.dropFirst().elementsEqual(["--supervised-test"]),
                enabled: ProcessInfo.processInfo.environment["KENN_EXPERIMENTAL_LIVE_EXPORT"] == "1")
            let data = try JSONEncoder().encode(receipt)
            FileHandle.standardOutput.write(data + Data([10]))
        } catch {
            // Malformed input cannot supply trustworthy receipt fields. Emit a bounded protocol error only.
            let data = Data("{\"schema\":\"kenn.live_export_receipt.v1\",\"status\":\"failed\",\"writer_closed\":false,\"error_code\":\"invalid_request\",\"error\":\"Malformed or oversized export request.\"}\n".utf8)
            FileHandle.standardOutput.write(data)
        }
    }
}
#endif
