import Foundation

/// Deterministic, safe filename sanitiser.
/// Preserves useful Unicode (accented names) while removing filesystem-hostile content.
public enum FilenameSanitizer {
    /// Characters forbidden on macOS/Windows/common cloud drives.
    static let forbidden = CharacterSet(charactersIn: "/\\:*?\"<>|")
    public static let defaultMaxBaseLength = 180 // bytes-safe conservative cap below 255

    /// Reject names that could escape the intended directory or collide with
    /// reserved cross-platform device names. Template rendering sanitises
    /// ordinary punctuation; direct file-operation callers must still be
    /// checked at the boundary.
    public static func invalidBaseNameReason(_ input: String) -> String? {
        guard !input.isEmpty else { return "The filename cannot be empty." }
        if input == "." || input == ".." {
            return "That filename is reserved."
        }
        if input.contains("/") || input.contains("\\") {
            return "Filename paths are not allowed."
        }
        if input.unicodeScalars.contains(where: {
            $0.value < 32 || $0.value == 127
        }) {
            return "Control characters are not allowed in filenames."
        }
        if input.hasSuffix(".") || input.hasSuffix(" ") {
            return "Filenames cannot end with a period or space."
        }
        let stem = input.split(separator: ".", maxSplits: 1, omittingEmptySubsequences: true)
            .first.map(String.init)?.uppercased() ?? input.uppercased()
        let reserved = Set(["CON", "PRN", "AUX", "NUL",
                            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"])
        if reserved.contains(stem) {
            return "That filename is reserved by the operating system."
        }
        return nil
    }

    public enum CaseStyle: String, Codable, CaseIterable, Sendable {
        case keepOriginal = "keep"
        case titleCase = "title_case"
        case snakeCase = "snake_case"
        case kebabCase = "kebab_case"
        case safeSpaces = "safe_spaces"

        public var displayName: String {
            switch self {
            case .keepOriginal: return "Keep original case"
            case .titleCase: return "Title_Case"
            case .snakeCase: return "snake_case"
            case .kebabCase: return "kebab-case"
            case .safeSpaces: return "Safe Spaces"
            }
        }
    }

    public static func sanitize(_ input: String,
                                maxBaseLength: Int = defaultMaxBaseLength,
                                caseStyle: CaseStyle = .keepOriginal) -> String {
        var s = input.precomposedStringWithCanonicalMapping

        // Strip control characters and default-ignorables.
        s.unicodeScalars.removeAll { scalar in
            scalar.value < 32 || scalar.value == 127 ||
            scalar.properties.isDefaultIgnorableCodePoint
        }

        // Forbidden characters → underscore (single separator).
        var replaced = ""
        for scalar in s.unicodeScalars {
            if forbidden.contains(scalar) {
                replaced.append("_")
            } else {
                replaced.unicodeScalars.append(scalar)
            }
        }
        s = replaced

        // Apply case style on word boundaries.
        s = applyCase(s, style: caseStyle)

        // Collapse duplicate whitespace / underscores / hyphens.
        s = s.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        s = s.replacingOccurrences(of: #"_+"#, with: "_", options: .regularExpression)
        s = s.replacingOccurrences(of: #"(\s*[_-]\s*){2,}"#, with: "_", options: .regularExpression)
        if caseStyle == .snakeCase { s = s.replacingOccurrences(of: " ", with: "_") }
        if caseStyle == .kebabCase { s = s.replacingOccurrences(of: " ", with: "-") }

        s = s.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_-. "))
        while s.hasPrefix(".") { s.removeFirst() }
        while s.hasSuffix(".") { s.removeLast() }
        s = s.trimmingCharacters(in: .whitespaces)

        // Length cap without splitting grapheme clusters.
        if let truncated = truncate(s, to: maxBaseLength) { s = truncated }
        if s.isEmpty { s = "Untitled" }
        return s
    }

    static func applyCase(_ s: String, style: CaseStyle) -> String {
        switch style {
        case .keepOriginal:
            return s
        case .titleCase:
            return s.split(separator: " ", omittingEmptySubsequences: true)
                .map { $0.prefix(1).uppercased() + $0.dropFirst().lowercased() }
                .joined(separator: "_")
        case .snakeCase:
            return s.lowercased()
        case .kebabCase:
            return s.lowercased()
        case .safeSpaces:
            return s
        }
    }

    /// Grapheme-safe truncation.
    static func truncate(_ s: String, to byteLimit: Int) -> String? {
        guard s.utf8.count > byteLimit else { return nil }
        var out = ""
        for ch in s {
            if (out + String(ch)).utf8.count > byteLimit { break }
            out.append(ch)
        }
        return String(out.drop(while: { $0 == " " || $0 == "_" }))
            .trimmingCharacters(in: CharacterSet(charactersIn: "_- "))
    }
}
