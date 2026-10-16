import ApplicationServices
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
