import Foundation

/// Supported media and document file formats for NITE Submit inspection.
public enum FileKind: String, Codable, Sendable {
    case pdf = "pdf"
    case docx = "docx"
    case audioWav = "wav"
    case videoMp4 = "mp4"
    case videoMov = "mov"
    case archiveZip = "zip"
    case archive7z = "7z"
    case unknown = "unknown"

    public var displayName: String {
        switch self {
        case .pdf: return "PDF Document"
        case .docx: return "Word Document"
        case .audioWav: return "WAVE Audio"
        case .videoMp4: return "MP4 Video"
        case .videoMov: return "QuickTime Video"
        case .archiveZip: return "ZIP Archive"
        case .archive7z: return "7z Archive"
        case .unknown: return "File Asset"
        }
    }

    public static func detect(url: URL) -> FileKind {
        switch url.pathExtension.lowercased() {
        case "pdf": return .pdf
        case "docx", "doc": return .docx
        case "wav", "aiff", "flac": return .audioWav
        case "mp4", "m4v": return .videoMp4
        case "mov": return .videoMov
        case "zip": return .archiveZip
        case "7z": return .archive7z
        default: return .unknown
        }
    }
}

/// Metadata inspector for non-PDF media assets (.wav, .mp4, .mov, etc.).
public struct MediaExtractor: Sendable {
    public init() {}

    /// Extracts available metadata fields from a media file or general asset.
    public func extractMetadata(at url: URL) -> SubmissionMetadata {
        var metadata = SubmissionMetadata()
        let filename = url.deletingPathExtension().lastPathComponent
        let kind = FileKind.detect(url: url)

        // Attempt filename pattern matching for student ID / module code / title
        if let idMatch = extractStudentId(from: filename) {
            metadata.studentId = Detection(value: idMatch, confidence: .medium,
                                           source: "Extracted from filename pattern", rule: "filename_id_regex")
        }

        if let moduleMatch = extractModuleCode(from: filename) {
            metadata.moduleCode = Detection(value: moduleMatch, confidence: .medium,
                                            source: "Extracted from filename pattern", rule: "filename_module_regex")
        }

        let cleanTitle = sanitizeTitleFromFilename(filename)
        if !cleanTitle.isEmpty {
            metadata.projectTitle = Detection(value: cleanTitle, confidence: .medium,
                                              source: "Derived from file asset name: \(kind.displayName)",
                                              rule: "filename_title_derivation")
        }

        return metadata
    }

    private func extractStudentId(from filename: String) -> String? {
        let pattern = #"(?:^|[^0-9A-Za-z])([0-9]{6,10})(?:[^0-9A-Za-z]|$)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(filename.startIndex..<filename.endIndex, in: filename)
        if let match = regex.firstMatch(in: filename, range: range),
           let r = Range(match.range(at: 1), in: filename) {
            return String(filename[r])
        }
        return nil
    }

    private func extractModuleCode(from filename: String) -> String? {
        let pattern = #"(?:^|[^0-9A-Za-z])([A-Za-z]{3,4}[0-9]{3,4})(?:[^0-9A-Za-z]|$)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(filename.startIndex..<filename.endIndex, in: filename)
        if let match = regex.firstMatch(in: filename, range: range),
           let r = Range(match.range(at: 1), in: filename) {
            return String(filename[r]).uppercased()
        }
        return nil
    }

    private func sanitizeTitleFromFilename(_ filename: String) -> String {
        var clean = filename
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
        // Remove trailing or leading digit sequences
        let pattern = #"[0-9]{6,10}|[A-Za-z]{3,4}[0-9]{3,4}"#
        if let regex = try? NSRegularExpression(pattern: pattern) {
            let range = NSRange(clean.startIndex..<clean.endIndex, in: clean)
            clean = regex.stringByReplacingMatches(in: clean, range: range, withTemplate: "")
        }
        clean = clean.trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.isEmpty ? filename : clean
    }
}

