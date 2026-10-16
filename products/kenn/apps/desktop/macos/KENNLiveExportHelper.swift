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
        // Match the backend's ASCII 6/2/2 digit contract, including padded nonzero values.
        guard parts.count == 3,
              zip(parts, [6, 2, 2]).allSatisfy({ part, limit in
                  !part.isEmpty && part.utf8.count <= limit && part.utf8.allSatisfy { (48...57).contains($0) }
              }),
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

    /// Normalizes exact numeric toggle states; unknown values must fail profile comparison.
    static func settingValue(identifier: String, value: CFTypeRef) -> String {
        if ["On", "Off"].contains(fixedSettings[identifier]), let number = value as? NSNumber,
           [0.0, 1.0].contains(number.doubleValue) {
            // Truncating a fractional AX value would silently qualify an unknown toggle state.
            return number.doubleValue == 0 ? "Off" : "On"
        }
        // Unknown toggle states and other settings reach profile comparison without coercion.
        return String(describing: value)
    }

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

/// Metadata for one owned WAV generation; timestamps also reject same-inode, same-size rewrites.
struct ExportFileIdentity: Equatable {
    let device: dev_t
    let inode: ino_t
    let size: off_t
    let mode: mode_t
    let modifiedSeconds: time_t
    let modifiedNanoseconds: Int
    let changedSeconds: time_t
    let changedNanoseconds: Int

    init?(_ info: stat) {
        guard info.st_mode & S_IFMT == S_IFREG, info.st_uid == getuid(), info.st_nlink == 1, info.st_size >= 0 else {
            // Links, foreign ownership and nonregular files cannot identify a job-owned render.
            return nil
        }
        device = info.st_dev
        inode = info.st_ino
        size = info.st_size
        mode = info.st_mode
        modifiedSeconds = info.st_mtimespec.tv_sec
        modifiedNanoseconds = info.st_mtimespec.tv_nsec
        changedSeconds = info.st_ctimespec.tv_sec
        changedNanoseconds = info.st_ctimespec.tv_nsec
    }

    static func at(_ path: String) -> Self? {
        var info = stat()
        guard lstat(path, &info) == 0 else { return nil } // Missing/inaccessible paths leave the generation unknown.
        return Self(info)
    }
}

struct ExportDescriptorEvidence {
    let identity: ExportFileIdentity
    let hasNoOpenDescriptor: Bool
}

/// Completion binds parser and descriptor evidence to the same unchanged file generation.
struct ExportCompletionEvidence {
    let observedExportProgress: Bool
    let exportDialogsGone: Bool
    let validWAV: ExportFileIdentity?
    let writer: ExportDescriptorEvidence?

    var permitsPublication: Bool {
        guard let identity = validWAV, let writer else { return false } // Partial or inaccessible evidence cannot qualify completion.
        return observedExportProgress && exportDialogsGone && writer.identity == identity && writer.hasNoOpenDescriptor
    }
}

/// Checks the exact PCM format without loading an entire arrangement into memory.
enum ExportWAV {
    static let maximumBytes: UInt64 = 150 * 1_024 * 1_024 // 150 MiB matches the existing offline upload ceiling.
    static let maximumFrames: UInt64 = 48_000 * 8 * 60 // Eight minutes at 48 kHz matches offline analysis.

    @discardableResult
    static func validate(_ path: String, readBytes: (FileHandle, Int) throws -> Data = { try $0.read(upToCount: $1) ?? Data() }) throws -> ExportFileIdentity {
        guard let identity = ExportFileIdentity.at(path), identity.size >= 44, UInt64(identity.size) <= maximumBytes else {
            throw ExportProblem.invalid("The completed WAV must be an owned, single-link regular file within the 150 MiB limit.")
        }
        let descriptor = open(path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else { throw ExportProblem.invalid("The WAV could not be opened without following a symbolic link.") }
        let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? file.close() } // Validation owns only its read handle, never Live's writer.
        var opened = stat()
        guard fstat(descriptor, &opened) == 0, ExportFileIdentity(opened) == identity else {
            throw ExportProblem.invalid("The WAV identity changed during validation.")
        }
        func read(_ count: Int) throws -> Data {
            let bytes = try readBytes(file, count)
            guard bytes.count == count else { throw ExportProblem.invalid("The WAV is truncated.") }
            return bytes
        }
        let header = try read(12)
        guard String(data: header.prefix(4), encoding: .ascii) == "RIFF",
              String(data: header.suffix(4), encoding: .ascii) == "WAVE",
              UInt64(u32(header, 4)) + 8 == UInt64(identity.size) else {
            throw ExportProblem.invalid("A finalized RIFF/WAVE header is required; RF64 is not qualified.")
        }
        var validFormat = false
        var dataBytes: UInt64 = 0
        var offset: UInt64 = 12 // RIFF's identifier, length and WAVE identifier occupy 12 bytes.
        while offset + 8 <= UInt64(identity.size) {
            try file.seek(toOffset: offset)
            let chunk = try read(8)
            let length = UInt64(u32(chunk, 4))
            let payload = offset + 8
            guard payload + length <= UInt64(identity.size) else { throw ExportProblem.invalid("The WAV chunk extends beyond the file.") }
            let name = String(data: chunk.prefix(4), encoding: .ascii)
            if name == "fmt " {
                guard !validFormat, length == 16 else { throw ExportProblem.invalid("Only one 16-byte PCM format chunk is qualified.") }
                let format = try read(16)
                validFormat = u16(format, 0) == 1 && u16(format, 2) == 2 && u32(format, 4) == 48_000
                    && u32(format, 8) == 288_000 && u16(format, 12) == 6 && u16(format, 14) == 24
                // Stereo 24-bit PCM has six bytes per frame and 288000 bytes per second at 48 kHz.
                guard validFormat else { throw ExportProblem.invalid("The WAV must be stereo 48000 Hz, 24-bit PCM.") }
            } else if name == "data" {
                guard dataBytes == 0, length > 0, length % 6 == 0, length / 6 <= maximumFrames else {
                    throw ExportProblem.invalid("One nonempty, frame-aligned audio chunk of at most eight minutes is required.")
                }
                dataBytes = length
            }
            offset = payload + length + length % 2 // RIFF chunks use even-byte padding.
        }
        guard validFormat, dataBytes > 0, offset == UInt64(identity.size) else {
            throw ExportProblem.invalid("The WAV has incomplete format, audio or trailing chunk data.")
        }
        var finished = stat()
        guard fstat(descriptor, &finished) == 0, ExportFileIdentity(finished) == identity,
              ExportFileIdentity.at(path) == identity else {
            throw ExportProblem.invalid("The WAV changed while its headers were being validated.")
        }
        return identity
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

/// Rechecks the validated generation around inspection; nil never proves the writer closed.
func inspectLiveOutputDescriptors(pid: Int32, outputPath: String, expected: ExportFileIdentity,
                                  inspect: (Int32, ExportFileIdentity) -> Bool? = processHasNoOpenOutputDescriptor) -> ExportDescriptorEvidence? {
    guard pid > 0, ExportFileIdentity.at(outputPath) == expected else { return nil } // Validation of A must not qualify a later B.
    guard let closed = inspect(pid, expected), ExportFileIdentity.at(outputPath) == expected else {
        // A failed snapshot or a concurrent rewrite leaves the writer/file association unproven.
        return nil
    }
    return ExportDescriptorEvidence(identity: expected, hasNoOpenDescriptor: closed)
}

private func processHasNoOpenOutputDescriptor(pid: Int32, expected: ExportFileIdentity) -> Bool? {
    let entrySize = MemoryLayout<proc_fdinfo>.stride
    let needed = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, nil, 0)
    guard needed > 0, needed <= 16_384 * entrySize, Int(needed) % entrySize == 0 else {
        return nil // Failed, malformed or over-16384-descriptor snapshots cannot prove closure.
    }
    var entries = [proc_fdinfo](repeating: proc_fdinfo(), count: Int(needed) / entrySize + 32)
    let capacity = entries.count * entrySize // 32 entries of headroom detect growth without an unbounded retry loop.
    let actual = entries.withUnsafeMutableBytes { proc_pidinfo(pid, PROC_PIDLISTFDS, 0, $0.baseAddress, Int32(capacity)) }
    guard actual > 0, actual < capacity, actual <= 16_384 * entrySize, Int(actual) % entrySize == 0 else {
        return nil // Filled or partial buffers are incomplete even when every returned entry looks unrelated.
    }
    for entry in entries.prefix(Int(actual) / entrySize) where entry.proc_fdtype == PROX_FDTYPE_VNODE {
        var vnode = vnode_fdinfowithpath()
        let bytes = proc_pidfdinfo(pid, entry.proc_fd, PROC_PIDFDVNODEPATHINFO, &vnode, Int32(MemoryLayout.size(ofValue: vnode)))
        guard bytes == MemoryLayout.size(ofValue: vnode) else { return nil } // A racing or inaccessible descriptor leaves closure unproven.
        // Device/inode identity also catches macOS's /var versus /private/var aliases and hard links.
        let identity = vnode.pvip.vip_vi.vi_stat
        if identity.vst_dev == expected.device && identity.vst_ino == expected.inode { return false }
    }
    return true
}

/// Keeps process checks, reads and presses injectable together; the executable always uses native defaults.
struct LiveExportEnvironment {
    var trusted: () -> Bool = AXIsProcessTrusted
    var isLive: (Int32) -> Bool = { pid in
        guard let running = NSRunningApplication(processIdentifier: pid) else { return false } // A missing process has no export authority.
        return running.bundleIdentifier == "com.ableton.live" && !running.isTerminated
    }
    var reader: (Date) -> ExportAXReader = { ExportAXReader(deadline: $0) }
    var press: (AXUIElement) -> AXError = { AXUIElementPerformAction($0, kAXPressAction as CFString) }
    var now: () -> Date = Date.init
    var sleep: (TimeInterval) -> Void = { Thread.sleep(forTimeInterval: $0) }
}

/// Restricts AX actions to a verified Ableton process and the one dialog this invocation opens.
final class LiveExportAccessibility {
    private let request: LiveExportRequest
    private let app: AXUIElement
    private var openedDialog: AXUIElement?
    private var ownedCancel: AXUIElement?
    private var mainWindow: AXUIElement?
    private var baselineWindows: [AXUIElement] = []
    private var used = false
    private let deadline: Date
    private let environment: LiveExportEnvironment

    init(_ request: LiveExportRequest, environment: LiveExportEnvironment = LiveExportEnvironment()) {
        self.request = request
        self.environment = environment
        app = AXUIElementCreateApplication(request.live_pid)
        deadline = environment.now().addingTimeInterval(Double(request.timeout_seconds))
        AXUIElementSetMessagingTimeout(app, 2) // Two seconds bounds an unresponsive Live AX request.
    }

    func run(supervised: Bool, enabled: Bool) -> LiveExportReceipt {
        var receipt = LiveExportReceipt(request, problem: .unavailable("export_profile_unqualified", "Live's export range, settings and destination AX controls require supervised qualification."))
        guard !used else {
            // A second invocation must not replace ownership evidence from an unresolved first dialog.
            return LiveExportReceipt(request, problem: .unavailable("request_already_used", "Each helper instance accepts only one bounded request."))
        }
        used = true
        do {
            try request.validate()
            guard request.action == "inspect" || (supervised && enabled) else {
                throw ExportProblem.unavailable("experimental_export_disabled", "Export requires KENN_EXPERIMENTAL_LIVE_EXPORT=1 and --supervised-test; production export is disabled.")
            }
            guard environment.trusted() else {
                throw ExportProblem.unavailable("accessibility_not_granted", "Accessibility access is unavailable; this helper does not request or change permissions.")
            }
            baselineWindows = try verifyLive(using: reader)
            if request.action == "inspect" {
                // Inspection never opens a menu or a dialog, even when the experimental gate is enabled.
                return receipt
            }
            try checkCancellation()
            guard try dialogs(in: baselineWindows, using: reader).isEmpty else {
                throw ExportProblem.unavailable("existing_dialog", "Close existing Live dialogs before a supervised export check.")
            }
            let menuBar = try element(app, kAXMenuBarAttribute)
            let file = try unique(try children(menuBar), title: "File")
            let exportItems = try reader.nodes(roots: [file]).filter { try ["Export Audio/Video…", "Export Audio/Video..."].contains(title($0)) }
            guard exportItems.count == 1 else {
                throw ExportProblem.unavailable("export_menu_unavailable", "The fixed File > Export Audio/Video menu item is missing or ambiguous.")
            }
            try checkCancellation() // Recheck after tree reads; a cancelled or expired request must not open a dialog.
            let beforePress = try verifyLive(using: reader)
            guard sameWindows(beforePress, baselineWindows), try dialogs(in: beforePress, using: reader).isEmpty else {
                throw ExportProblem.unavailable("window_identity_changed", "Live's windows changed before the export menu action.")
            }
            try checkCancellation()
            guard environment.press(exportItems[0]) == .success else {
                throw ExportProblem.unavailable("export_menu_rejected", "Live did not accept the export menu action.")
            }
            var acquisitionDeadline = deadline
            var acquisitionCancelled = false
            while environment.now() < acquisitionDeadline {
                // Cancellation after the menu press still needs bounded acquisition of the new dialog for cleanup.
                if cancellationRequested(), !acquisitionCancelled {
                    acquisitionCancelled = true
                    acquisitionDeadline = min(deadline, environment.now().addingTimeInterval(2)) // Two seconds is the post-cancel acquisition grace.
                }
                let acquisitionReader = environment.reader(acquisitionDeadline)
                let current: [AXUIElement]
                do { current = try verifyLive(using: acquisitionReader) } catch {
                    // A late AX reply cannot turn a cancelled, still-unidentified dialog into a clean disappearance.
                    if acquisitionCancelled, environment.now() >= acquisitionDeadline {
                        throw ExportProblem(status: "cancelled", code: "cancel_acquisition_unresolved", message: "Cancellation stopped bounded dialog acquisition; a delayed or unidentified Live dialog may remain open.")
                    }
                    throw error
                }
                guard baselineWindows.allSatisfy({ original in current.contains(where: { CFEqual($0, original) }) }) else {
                    throw ExportProblem.unavailable("window_identity_changed", "An original Live window disappeared during export-dialog acquisition.")
                }
                let added = current.filter { candidate in !baselineWindows.contains(where: { CFEqual($0, candidate) }) }
                let currentDialogs = try dialogs(in: current, using: acquisitionReader)
                if added.count == 1, current.count == baselineWindows.count + 1,
                   currentDialogs.count == 1, CFEqual(currentDialogs[0], added[0]) {
                    let cancel = try verifiedCancel(in: added[0], using: acquisitionReader)
                    openedDialog = added[0]
                    ownedCancel = cancel
                    receipt.owned_dialog = true
                    break
                }
                guard added.isEmpty, currentDialogs.isEmpty else {
                    throw ExportProblem.unavailable("ambiguous_export_dialog", "The observed window transition does not identify one new top-level export dialog.")
                }
                environment.sleep(min(0.1, max(0, acquisitionDeadline.timeIntervalSince(environment.now())))) // At most 100 ms per acquisition poll.
            }
            guard openedDialog != nil else {
                if acquisitionCancelled {
                    throw ExportProblem(status: "cancelled", code: "cancel_acquisition_unresolved", message: "Cancellation stopped bounded dialog acquisition; a delayed or unidentified Live dialog may remain open.")
                }
                throw ExportProblem.unavailable("export_dialog_unavailable", "Live did not expose an identifiable Export Audio/Video AX dialog before the deadline.")
            }
            try checkCancellation()
            if let dialog = openedDialog {
                var values: [String: [String]] = [:]
                for node in try reader.nodes(roots: [dialog]) {
                    if let identifier = try reader.string(node, kAXIdentifierAttribute),
                       let value = try reader.value(node, kAXValueAttribute) {
                        values[identifier, default: []].append(LiveExportProfile.settingValue(identifier: identifier, value: value))
                    }
                }
                try LiveExportProfile.validate(values: values, request: request)
            }
            try checkCancellation() // Profile reads must not hide a cancellation or deadline that arrived during inspection.
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

    private func verifyLive(using reader: ExportAXReader) throws -> [AXUIElement] {
        guard environment.trusted() else {
            throw ExportProblem.unavailable("accessibility_not_granted", "Accessibility access is no longer available.")
        }
        guard environment.isLive(request.live_pid) else {
            throw ExportProblem.unavailable("live_identity_mismatch", "The requested process is not a running Ableton Live application.")
        }
        let current = try reader.elements(app, kAXWindowsAttribute)
        guard sameWindows(current, current) else {
            throw ExportProblem.unavailable("window_identity_mismatch", "Live returned duplicate window identities.")
        }
        let matches = try current.filter { try reader.string($0, kAXTitleAttribute) == request.expected_window_title }
        guard matches.count == 1 else {
            throw ExportProblem.unavailable("window_identity_mismatch", "The exact expected Live window is missing or ambiguous.")
        }
        guard try reader.string(matches[0], kAXRoleAttribute, required: true) == kAXWindowRole,
              try reader.string(matches[0], kAXSubroleAttribute, required: true) == kAXStandardWindowSubrole else {
            throw ExportProblem.unavailable("window_identity_mismatch", "The exact Live main window must retain its native standard-window role.")
        }
        if let expected = mainWindow, !CFEqual(expected, matches[0]) {
            // A replacement window with the same title is a different session observation.
            throw ExportProblem.unavailable("window_identity_changed", "The original exact Live window was replaced.")
        }
        mainWindow = matches[0]
        return current
    }

    private func checkCancellation() throws {
        guard environment.now() < deadline else {
            throw ExportProblem.unavailable("accessibility_deadline", "The export request deadline expired before an action.")
        }
        if cancellationRequested() {
            throw ExportProblem(status: "cancelled", code: "cancel_requested", message: "The job owner requested cancellation.")
        }
    }

    private func cancellationRequested() -> Bool {
        let marker = URL(fileURLWithPath: request.output_path).deletingLastPathComponent().appendingPathComponent("cancel.requested")
        var info = stat()
        // A present or unreadable marker cannot authorize another operation, including broken links.
        return lstat(marker.path, &info) == 0 || errno != ENOENT
    }

    private func cancelOwnedDialog() -> String? {
        guard let dialog = openedDialog else { return nil } // Never dismiss a dialog that predates this helper.
        // This two-second acceptance budget cannot interrupt an in-flight AX operation; late replies still reject.
        let cancelDeadline = environment.now().addingTimeInterval(2)
        let cleanupReader = environment.reader(cancelDeadline)
        do {
            var current = try verifyLive(using: cleanupReader)
            if !current.contains(where: { CFEqual($0, dialog) }) {
                guard sameWindows(current, baselineWindows), try dialogs(in: current, using: cleanupReader).isEmpty else {
                    return "The owned dialog disappeared into an unqualified window state."
                }
                return nil // Independently observed disappearance needs no retained-button action.
            }
            try verifyOwnedWindows(current, dialog: dialog, using: cleanupReader)
            let cancel = try verifiedCancel(in: dialog, using: cleanupReader)
            try verifyOwnedWindows(verifyLive(using: cleanupReader), dialog: dialog, using: cleanupReader)
            guard let original = ownedCancel, CFEqual(cancel, original), environment.trusted(), environment.isLive(request.live_pid), environment.now() < cancelDeadline,
                  environment.press(cancel) == .success else {
                return "The helper-owned export dialog could not be cancelled through its unchanged exact Cancel control."
            }
            while environment.now() < cancelDeadline {
                current = try verifyLive(using: cleanupReader)
                if !current.contains(where: { CFEqual($0, dialog) }) {
                    guard sameWindows(current, baselineWindows), try dialogs(in: current, using: cleanupReader).isEmpty else {
                        return "Cancellation exposed an unqualified replacement dialog or window."
                    }
                    return nil
                }
                try verifyOwnedWindows(current, dialog: dialog, using: cleanupReader)
                environment.sleep(min(0.05, max(0, cancelDeadline.timeIntervalSince(environment.now())))) // At most 50 ms; never repeat the press.
            }
        } catch {
            // Unknown process/window/control state cannot justify pressing a retained node or claiming disappearance.
            return "The helper-owned dialog's process, window or Cancel identity could not be revalidated."
        }
        return "The Cancel action was accepted but disappearance of the helper-owned dialog was not verified."
    }

    private func sameWindows(_ first: [AXUIElement], _ second: [AXUIElement]) -> Bool {
        first.count == second.count && first.allSatisfy { node in second.filter { CFEqual($0, node) }.count == 1 }
    }

    private func verifyOwnedWindows(_ current: [AXUIElement], dialog: AXUIElement, using reader: ExportAXReader) throws {
        let currentDialogs = try dialogs(in: current, using: reader)
        guard sameWindows(current, baselineWindows + [dialog]), currentDialogs.count == 1, CFEqual(currentDialogs[0], dialog) else {
            throw ExportProblem.unavailable("dialog_identity_changed", "The owned export dialog is no longer the sole new Live window and dialog.")
        }
    }

    private func verifiedCancel(in dialog: AXUIElement, using reader: ExportAXReader) throws -> AXUIElement {
        guard try reader.string(dialog, kAXRoleAttribute, required: true) == kAXWindowRole,
              try reader.string(dialog, kAXSubroleAttribute, required: true) == kAXDialogSubrole,
              try reader.string(dialog, kAXTitleAttribute, required: true) == "Export Audio/Video" else {
            throw ExportProblem.unavailable("export_dialog_unqualified", "The new window does not match the qualified top-level export profile.")
        }
        let matches = try reader.nodes(roots: [dialog]).filter {
            try reader.string($0, kAXIdentifierAttribute) == "Base.FinalButtonsBox.CancelButton"
        }
        guard matches.count == 1, try reader.string(matches[0], kAXRoleAttribute, required: true) == kAXButtonRole,
              let value = try reader.value(matches[0], kAXEnabledAttribute, required: true), CFGetTypeID(value) == CFBooleanGetTypeID(),
              CFBooleanGetValue(unsafeBitCast(value, to: CFBoolean.self)) else {
            throw ExportProblem.unavailable("export_cancel_unqualified", "The exact unique Cancel button must have its native role and Boolean enabled state.")
        }
        // These complete observations bracket an action; AX provides no atomic read-and-press operation.
        return matches[0]
    }

    private var reader: ExportAXReader { environment.reader(deadline) }

    private func dialogs(in windows: [AXUIElement], using reader: ExportAXReader) throws -> [AXUIElement] {
        try reader.nodes(roots: windows).filter { node in
            let role = try reader.string(node, kAXRoleAttribute, required: true)
            if role == kAXSheetRole { return true }
            return try reader.string(node, kAXSubroleAttribute, required: role == kAXWindowRole) == kAXDialogSubrole
        }
    }
    private func title(_ node: AXUIElement) throws -> String { try reader.string(node, kAXTitleAttribute) ?? "" }
    private func children(_ node: AXUIElement) throws -> [AXUIElement] {
        try reader.elements(node, kAXChildrenAttribute, allowAbsent: true)
    }
    private func element(_ node: AXUIElement, _ key: String) throws -> AXUIElement {
        guard let value = try reader.value(node, key, required: true), CFGetTypeID(value) == AXUIElementGetTypeID() else {
            throw ExportProblem.unavailable("inaccessible_menu", "Live did not expose the required native menu.")
        }
        return unsafeBitCast(value, to: AXUIElement.self)
    }
    private func unique(_ nodes: [AXUIElement], title expected: String) throws -> AXUIElement {
        let matches = try nodes.filter { try title($0) == expected }
        guard matches.count == 1 else { throw ExportProblem.unavailable("ambiguous_menu", "The fixed File menu is missing or ambiguous.") }
        return matches[0]
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
