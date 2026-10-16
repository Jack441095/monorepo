import ApplicationServices
import Darwin
import Foundation

/// Reads the export UI through one injectable boundary; fixtures never query or act on Live.
struct ExportAXReader {
    static let maximumNodes = 2_048 // Shared node budget across all windows, including roots.
    var deadline: Date
    var now: () -> Date = Date.init
    var copyValue: (AXUIElement, String) -> (AXError, CFTypeRef?) = { node, key in
        var value: CFTypeRef?
        let error = AXUIElementCopyAttributeValue(node, key as CFString, &value)
        return (error, value)
    }
    var countValues: (AXUIElement, String) -> (AXError, Int) = { node, key in
        var count = 0
        let error = AXUIElementGetAttributeValueCount(node, key as CFString, &count)
        return (error, count)
    }
    var copyValues: (AXUIElement, String, Int) -> (AXError, CFTypeRef?) = { node, key, limit in
        var values: CFArray?
        let error = AXUIElementCopyAttributeValues(node, key as CFString, 0, limit, &values)
        return (error, values)
    }

    func value(_ node: AXUIElement, _ key: String, required: Bool = false) throws -> CFTypeRef? {
        try checkDeadline()
        let (error, value) = copyValue(node, key)
        try checkDeadline() // An IPC call can finish after the deadline even if it started in time.
        if !required, error == .attributeUnsupported || error == .noValue {
            // Only explicit attribute absence is optional; messaging failures never mean absence.
            return nil
        }
        guard error == .success, let value else { throw readFailure(key) }
        return value
    }

    func string(_ node: AXUIElement, _ key: String, required: Bool = false) throws -> String? {
        guard let value = try value(node, key, required: required) else { return nil } // Explicit optional absence has no text to match.
        guard let text = value as? String else { throw readFailure(key) }
        return text
    }

    func elements(_ node: AXUIElement, _ key: String, allowAbsent: Bool = false, limit: Int = maximumNodes) throws -> [AXUIElement] {
        try checkDeadline()
        guard (0...Self.maximumNodes).contains(limit) else { throw readFailure(key) }
        let (error, count) = countValues(node, key)
        try checkDeadline()
        if allowAbsent, error == .attributeUnsupported || error == .noValue {
            // Leaf controls may omit AXChildren; AXWindows is always required by the caller.
            return []
        }
        guard error == .success, count >= 0, count <= limit else { throw readFailure(key) }
        var result: [AXUIElement] = []
        if count > 0 {
            // One extra slot detects growth without asking AX to allocate an unbounded array.
            let (copyError, copied) = copyValues(node, key, count + 1)
            try checkDeadline()
            guard copyError == .success, let elements = copied as? [CFTypeRef], elements.count == count,
                  elements.allSatisfy({ CFGetTypeID($0) == AXUIElementGetTypeID() }) else {
                throw readFailure(key)
            }
            // Swift's Objective-C array cast alone accepts NSNumber as AXUIElement; check each CF type first.
            result = elements.map { unsafeBitCast($0, to: AXUIElement.self) }
        }
        let (finalError, finalCount) = countValues(node, key)
        try checkDeadline()
        guard finalError == .success, finalCount == count else { throw readFailure(key) }
        return result
    }

    /// Includes roots and rejects overflow rather than hiding unvisited controls or dialogs.
    func nodes(roots: [AXUIElement], limit: Int = maximumNodes) throws -> [AXUIElement] {
        try checkDeadline()
        guard (0...Self.maximumNodes).contains(limit), roots.count <= limit else { throw readFailure(kAXChildrenAttribute) }
        var queue = roots
        var index = 0
        while index < queue.count {
            let node = queue[index]
            index += 1
            // Even at the exact budget, check that the last node really has no further children.
            queue.append(contentsOf: try elements(node, kAXChildrenAttribute, allowAbsent: true, limit: limit - queue.count))
        }
        return queue
    }

    private func checkDeadline() throws {
        guard now() < deadline else {
            throw ExportProblem.unavailable("accessibility_deadline", "The export UI read exceeded the request deadline.")
        }
    }

    private func readFailure(_ key: String) -> ExportProblem {
        .unavailable("accessibility_read_incomplete", "The required export UI read failed, changed or exceeded its bound: \(key).")
    }
}

/// Checks a caller-associated Save panel without granting authority to press Save or dismiss it.
enum ExportSaveDestination {
    /// The caller must separately prove that this is its newly opened panel; no UI value is changed.
    static func validate(panel: AXUIElement, request: LiveExportRequest, reader: ExportAXReader) throws {
        try checkRequest(request, reader: reader)
        let parent = URL(fileURLWithPath: request.output_path).deletingLastPathComponent()
        let initialDirectory = try DirectoryIdentity(parent.path)
        let nodes = try reader.nodes(roots: [panel])
        var identifiers: [String: [AXUIElement]] = [:]
        for (index, node) in nodes.enumerated() {
            let role = try reader.string(node, kAXRoleAttribute, required: true)
            let subrole = try reader.string(node, kAXSubroleAttribute, required: role == kAXWindowRole)
            if index == 0 {
                guard role == kAXSheetRole || (role == kAXWindowRole && subrole == kAXDialogSubrole) else {
                    throw unknown("The supplied Save panel has an unqualified role.")
                }
            } else if role == kAXSheetRole || role == kAXWindowRole || subrole == kAXDialogSubrole {
                // An overwrite prompt or another nested dialog makes the destination state ambiguous.
                throw unknown("The Save panel contains another dialog or sheet.")
            }
            if let identifier = try reader.string(node, kAXIdentifierAttribute) {
                identifiers[identifier, default: []].append(node)
            }
        }
        let root = try unique("save-panel", in: identifiers)
        guard CFEqual(root, panel) else { throw unknown("The supplied root is not the unique native Save panel.") }
        let controls = ["saveAsNameTextField": kAXTextFieldRole, "where popup": kAXPopUpButtonRole,
                        "CancelButton": kAXButtonRole, "OKButton": kAXButtonRole, "ColumnView": kAXBrowserRole]
        for (identifier, role) in controls {
            let control = try unique(identifier, in: identifiers)
            guard try reader.string(control, kAXRoleAttribute, required: true) == role,
                  try enabled(control, reader: reader) else {
                throw unknown("A native Save control has an unqualified role or enabled state: \(identifier).")
            }
        }
        let filename = try unique("saveAsNameTextField", in: identifiers)
        guard try reader.string(filename, kAXValueAttribute, required: true) == "kenn-analysis.wav" else {
            throw unknown("The Save filename does not match the job's fixed output name.")
        }
        let browser = try unique("ColumnView", in: identifiers)
        guard let value = try reader.value(browser, kAXURLAttribute, required: true), CFGetTypeID(value) == CFURLGetTypeID() else {
            throw unknown("The native Save browser did not expose a URL-typed directory.")
        }
        let directory = unsafeBitCast(value, to: CFURL.self) as URL
        // Popup labels and child file URLs can name another location; only this browser's full URL qualifies.
        // Foundation may standardize an existing /private/var directory to /var; realpath supplies the canonical comparison.
        guard directory.isFileURL, directory.host == nil || directory.host == "",
              directory.query == nil, directory.fragment == nil, directory.path == parent.path,
              canonicalPath(directory.path) == parent.path else {
            throw unknown("The native Save browser is not in the exact canonical job directory.")
        }
        try checkRequest(request, reader: reader)
        guard try DirectoryIdentity(parent.path) == initialDirectory else {
            throw unknown("The job directory changed while its Save destination was inspected.")
        }
        try checkDeadline(reader)
    }

    private struct DirectoryIdentity: Equatable {
        let device: dev_t
        let inode: ino_t
        let owner: uid_t
        let mode: mode_t

        init(_ path: String) throws {
            var info = stat()
            guard canonicalPath(path) == path, lstat(path, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
                  info.st_uid == getuid(), info.st_mode & 0o7777 == 0o700 else {
                throw unknown("The Save destination must remain an owned canonical directory with mode 0700.")
            }
            // This snapshot proves stability only during this read, not job creation-time ownership or future Save authority.
            device = info.st_dev
            inode = info.st_ino
            owner = info.st_uid
            mode = info.st_mode
        }
    }

    private static func checkRequest(_ request: LiveExportRequest, reader: ExportAXReader) throws {
        try checkDeadline(reader)
        try request.validate() // Recheck absent output and bounded owned metadata on both sides of the UI inspection.
        var marker = stat()
        let path = URL(fileURLWithPath: request.output_path).deletingLastPathComponent().appendingPathComponent("cancel.requested").path
        guard lstat(path, &marker) != 0, errno == ENOENT else {
            // Presence or an unreadable marker cannot authorize further work, even if request validation allowed it as metadata.
            throw ExportProblem(status: "cancelled", code: "cancel_requested", message: "The job was cancelled before destination validation completed.")
        }
        try checkDeadline(reader)
    }

    private static func checkDeadline(_ reader: ExportAXReader) throws {
        guard reader.now() < reader.deadline else {
            throw ExportProblem.unavailable("accessibility_deadline", "The Save destination read exceeded the request deadline.")
        }
    }

    private static func unique(_ identifier: String, in nodes: [String: [AXUIElement]]) throws -> AXUIElement {
        guard let matches = nodes[identifier], matches.count == 1 else {
            throw unknown("A native Save control is missing or ambiguous: \(identifier).")
        }
        return matches[0]
    }

    private static func enabled(_ node: AXUIElement, reader: ExportAXReader) throws -> Bool {
        guard let value = try reader.value(node, kAXEnabledAttribute, required: true), CFGetTypeID(value) == CFBooleanGetTypeID() else {
            throw unknown("A native Save control did not expose a Boolean enabled state.")
        }
        return CFBooleanGetValue(unsafeBitCast(value, to: CFBoolean.self))
    }

    private static func unknown(_ message: String) -> ExportProblem {
        .unavailable("save_destination_unqualified", message)
    }
}
