import Foundation
import PDFKit
import AppKit
import Vision

/// Errors surfaced to the UI as friendly messages — never raw stack traces.
public enum PDFExtractError: Error, LocalizedError, Sendable {
    case fileMissing
    case unreadable
    case encrypted
    case empty

    public var errorDescription: String? {
        switch self {
        case .fileMissing: return "We couldn't find that file."
        case .unreadable: return "We couldn't read this PDF."
        case .encrypted: return "This PDF is password-protected."
        case .empty: return "This PDF appears to be empty."
        }
    }
}

/// Extracts structured text from a PDF using the system PDFKit parser.
/// Treats document content as untrusted data: no scripts are executed,
/// and extraction is bounded to avoid resource exhaustion.
public struct PDFExtractor: Sendable {
    /// Hard bounds so malformed/huge files can't exhaust memory.
    public var maxPages: Int
    public var maxCharactersPerPage: Int
    public var ocrMaxPages: Int
    public var ocrMaxDimension: CGFloat

    public init(maxPages: Int = 2000, maxCharactersPerPage: Int = 200_000,
                ocrMaxPages: Int = 3, ocrMaxDimension: CGFloat = 2200) {
        self.maxPages = maxPages
        self.maxCharactersPerPage = maxCharactersPerPage
        self.ocrMaxPages = ocrMaxPages
        self.ocrMaxDimension = ocrMaxDimension
    }

    public enum Outcome: Sendable {
        case success(PDFTextDocument)
        /// No usable embedded text — user must enter fields manually.
        case imageOnly(pageCount: Int)
    }

    public func extract(at url: URL) throws -> Outcome {
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw PDFExtractError.fileMissing
        }
        guard let doc = PDFDocument(url: url) else {
            if Self.looksEncrypted(at: url) { throw PDFExtractError.encrypted }
            throw PDFExtractError.unreadable
        }
        if doc.isLocked { throw PDFExtractError.encrypted }
        let pageCount = min(doc.pageCount, maxPages)
        if pageCount == 0 { throw PDFExtractError.empty }

        var pages: [PDFTextDocument.Page] = []
        var totalChars = 0
        // Page numbers that carried no usable text layer, i.e. scans. This has to
        // be tracked as we go rather than worked out from `pages` afterwards: a
        // page with no text layer never makes it into that array at all, so the
        // old allSatisfy({ $0.lines.isEmpty }) test could not see a scan sitting
        // behind a typed cover sheet and never looked for one.
        var scannedPageNumbers: [Int] = []
        for i in 0..<pageCount {
            guard let page = doc.page(at: i) else { continue }
            guard let fullText = page.string,
                  !fullText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                scannedPageNumbers.append(i + 1)
                continue
            }
            // Cut the raw page text down to the per-page budget *before* splitting
            // it into lines. PDFKit hands back the whole text layer in one string,
            // so a file with a hostile multi-megabyte page paid the full cost of
            // splitting it into a line array before anything threw most of it away.
            let raw = String(fullText.prefix(maxCharactersPerPage))
            let lines = Self.normaliseLines(raw)
                .prefix(maxCharactersPerPage / 40)
            for line in lines { totalChars += line.count }
            pages.append(PDFTextDocument.Page(pageNumber: i + 1, lines: Array(lines)))
            // Stop once we have read enough to fill the whole document's budget.
            // The per-page cap above is what actually bounds memory; this only
            // avoids grinding through thousands of pages once it is reached.
            if totalChars > maxCharactersPerPage * maxPages / 4 { break }
        }

        // Metadata is an untrusted hint; match keys defensively across SDK spellings.
        var metaTitle: String?
        var metaAuthor: String?
        for (key, value) in (doc.documentAttributes ?? [:]) {
            guard let s = value as? String else { continue }
            let k = "\(key)".lowercased()
            if k.contains("title") { metaTitle = s }
            if k.contains("author") { metaAuthor = s }
        }

        // A real submission is often a typed cover sheet followed by a scan of the
        // signed form, and the identity fields can be on the scan. Those pages were
        // never read, because the document had text somewhere and the old check
        // only asked whether everything it had kept was empty. Read the pages the
        // text layer did not cover and merge them into the same document, which
        // also covers the all-scans case on its own: with no embedded pages there
        // is nothing to merge into and `merged` is just the recognised pages.
        if !scannedPageNumbers.isEmpty {
            let recognised = Self.extractOCRPages(from: doc, pageNumbers: scannedPageNumbers,
                                                  maxPages: ocrMaxPages,
                                                  maxDimension: ocrMaxDimension)
            if !recognised.isEmpty {
                var merged = pages
                for page in recognised {
                    if let index = merged.firstIndex(where: { $0.pageNumber == page.pageNumber }) {
                        merged[index] = page
                    } else {
                        merged.append(page)
                    }
                }
                merged.sort { $0.pageNumber < $1.pageNumber }
                // Marked .ocr even when page 1 had a real text layer: the document
                // now contains recognised text, and the detector drops a notch of
                // confidence for anything it reads out of an OCR origin. Calling it
                // embedded text would let a guess off a scan reach the student as a
                // HIGH-confidence field.
                return .success(PDFTextDocument(
                    pageCount: doc.pageCount,
                    pages: merged,
                    metadataTitle: Self.cleanMetadata(metaTitle),
                    metadataAuthor: Self.cleanMetadata(metaAuthor),
                    textOrigin: .ocr
                ))
            }
            if pages.isEmpty {
                // Nothing on the pages, not even anything Vision could read.
                return .imageOnly(pageCount: doc.pageCount)
            }
        }
        return .success(PDFTextDocument(
            pageCount: doc.pageCount,
            pages: pages,
            metadataTitle: Self.cleanMetadata(metaTitle),
            metadataAuthor: Self.cleanMetadata(metaAuthor),
            textOrigin: .embeddedText
        ))
    }

    /// Bounded local OCR fallback for scanned PDFs. OCR is intentionally
    /// limited to the first few pages because filename-critical fields are
    /// normally on a cover/title page, and each page costs a second or more. It
    /// returns an empty array when Vision cannot produce usable text so callers
    /// can retain the manual-entry path. `pageNumbers` is 1-based, matching
    /// PDFTextDocument.Page.
    static func extractOCRPages(from doc: PDFDocument, pageNumbers: [Int],
                                maxPages: Int, maxDimension: CGFloat) -> [PDFTextDocument.Page] {
        guard maxPages > 0, maxDimension > 0 else { return [] }
        var pages: [PDFTextDocument.Page] = []
        for pageNumber in pageNumbers.prefix(maxPages) {
            guard let page = doc.page(at: pageNumber - 1),
                  let image = renderImage(for: page, maxDimension: maxDimension),
                  let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                continue
            }
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            request.recognitionLanguages = ["en-US", "en-GB"]
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            do {
                try handler.perform([request])
            } catch {
                continue
            }
            guard let observations = request.results, !observations.isEmpty else { continue }
            let lines = ocrLines(from: observations)
            if !lines.isEmpty {
                pages.append(PDFTextDocument.Page(pageNumber: pageNumber, lines: lines))
            }
        }
        return pages
    }

    static func renderImage(for page: PDFPage, maxDimension: CGFloat) -> NSImage? {
        let bounds = page.bounds(for: .mediaBox)
        guard bounds.width > 0, bounds.height > 0 else { return nil }
        let scale = min(maxDimension / bounds.width, maxDimension / bounds.height)
        let size = NSSize(width: max(1, bounds.width * scale),
                          height: max(1, bounds.height * scale))
        return page.thumbnail(of: size, for: .mediaBox)
    }

    static func ocrLines(from observations: [VNRecognizedTextObservation]) -> [String] {
        struct OCRItem {
            let x: CGFloat
            let y: CGFloat
            let text: String
        }
        let items = observations.compactMap { observation -> OCRItem? in
            guard let text = observation.topCandidates(1).first?.string else { return nil }
            return OCRItem(x: observation.boundingBox.minX,
                           y: observation.boundingBox.maxY,
                           text: text)
        }.sorted { lhs, rhs in
            if abs(lhs.y - rhs.y) > 0.025 { return lhs.y > rhs.y }
            return lhs.x < rhs.x
        }
        var groups: [(y: CGFloat, items: [OCRItem])] = []
        for item in items {
            if let index = groups.firstIndex(where: { abs($0.y - item.y) <= 0.025 }) {
                groups[index].items.append(item)
            } else {
                groups.append((item.y, [item]))
            }
        }
        return groups
            .sorted { $0.y > $1.y }
            .map { group in
                let joined = group.items.sorted { $0.x < $1.x }
                    .map(\.text)
                    .joined(separator: " ")
                return normaliseLines(joined).joined(separator: " ")
            }
            .filter { !$0.isEmpty }
    }

    /// Encrypted PDFs often fail PDFDocument(url:) silently; sniff the header.
    static func looksEncrypted(at url: URL) -> Bool {
        guard let data = try? Data(contentsOf: url, options: [.mappedIfSafe]),
              let head = String(data: data.prefix(2048), encoding: .isoLatin1) else { return false }
        return head.range(of: "/Encrypt") != nil
    }

    static func cleanMetadata(_ s: String?) -> String? {
        guard let s = s?.trimmingCharacters(in: .whitespacesAndNewlines),
              !s.isEmpty, !s.lowercased().contains("untitled") else { return nil }
        return s
    }

    /// Normalise weird whitespace and strip control characters from untrusted content.
    static func normaliseLines(_ raw: String) -> [String] {
        let cleaned = raw.precomposedStringWithCanonicalMapping
        return cleaned
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .components(separatedBy: "\n")
            .map { line -> String in
                var out = ""
                for ch in line {
                    let scalars = ch.unicodeScalars
                    if scalars.count == 1, scalars.first!.value < 32 { continue } // control chars
                    if scalars.allSatisfy({ $0.properties.isDefaultIgnorableCodePoint }) { continue }
                    out.append(ch)
                }
                // Tabs → spaces, collapse runs of whitespace.
                return out.replacingOccurrences(of: "\t", with: " ")
                    .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespaces)
            }
            .filter { !$0.isEmpty }
    }
}
