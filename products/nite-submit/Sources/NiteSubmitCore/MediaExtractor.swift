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
        let byExtension = kind(forExtension: url.pathExtension.lowercased())
        switch sniffHeader(at: url) {
        case .kind(let sniffed):
            // A .docx is a ZIP as far as its header is concerned, so the extension
            // is the only thing that can tell a Word file from an archive.
            if sniffed == .archiveZip, byExtension == .docx { return .docx }
            return sniffed
        case .notTheClaimedType:
            // The header is recognisable and it is not what the name says — an MP3
            // wearing a .wav name. We have no MP3 kind to give it, and the app has
            // no MP3 handling behind the label, so it becomes a plain asset rather
            // than something it is not.
            return .unknown
        case .noHeader:
            // Empty file, a format we do not sniff, or unreadable: the extension is
            // all we have, which is exactly what this did before.
            return byExtension
        }
    }

    private static func kind(forExtension ext: String) -> FileKind {
        switch ext {
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

    private enum HeaderVerdict {
        case kind(FileKind)
        case notTheClaimedType
        case noHeader
    }

    /// Decide from the container's own first 16 bytes. The extension is the one
    /// piece of evidence a file browser got wrong when someone renamed a file, so
    /// a recognised signature wins over the name.
    private static func sniffHeader(at url: URL) -> HeaderVerdict {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return .noHeader }
        defer { try? handle.close() }
        guard let head = try? handle.read(upToCount: 16), head.count >= 4 else { return .noHeader }
        let bytes = [UInt8](head)
        func starts(_ magic: [UInt8]) -> Bool { Array(bytes.prefix(magic.count)) == magic }
        func box(_ offset: Int, _ magic: [UInt8]) -> Bool {
            offset + magic.count <= bytes.count && Array(bytes[offset..<offset + magic.count]) == magic
        }

        if starts([0x25, 0x50, 0x44, 0x46]) { return .kind(.pdf) }            // %PDF
        if starts([0x37, 0x7A, 0xBC, 0xAF]) { return .kind(.archive7z) }       // 7z signature
        if starts([0x50, 0x4B, 0x03, 0x04]) { return .kind(.archiveZip) }      // PK.. local header
        if starts(Array("RIFF".utf8)), box(8, Array("WAVE".utf8)) { return .kind(.audioWav) }
        if starts(Array("FORM".utf8)), box(8, Array("AIFF".utf8)) { return .kind(.audioWav) }
        if box(4, Array("ftyp".utf8)) {
            // QuickTime and MP4 share the ftyp box; the brand right after it is
            // what separates them.
            return .kind(box(8, Array("qt  ".utf8)) ? .videoMov : .videoMp4)
        }
        if starts(Array("ID3".utf8)) { return .notTheClaimedType }            // MP3 with an ID3 tag
        if bytes[0] == 0xFF, bytes[1] & 0xE0 == 0xE0 { return .notTheClaimedType }  // MPEG frame sync
        return .noHeader
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

        // Attempt filename pattern matching for student ID / module code / title.
        // A number- or code-shaped token in a filename is the weakest evidence we
        // have: "IMG_20240115" and "TAKE1234" both match, and at MEDIUM confidence
        // either could be pasted straight into a submission filename and then into
        // a university upload form. These stay LOW and name their origin, so a
        // student is asked rather than told.
        if let idMatch = extractStudentId(from: filename) {
            metadata.studentId = Detection(value: idMatch, confidence: .low,
                                           source: "Student-number shape in the filename — please check",
                                           rule: "filename_id_regex")
        }

        if let moduleMatch = extractModuleCode(from: filename) {
            metadata.moduleCode = Detection(value: moduleMatch, confidence: .low,
                                            source: "Module-code shape in the filename — please check",
                                            rule: "filename_module_regex")
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

