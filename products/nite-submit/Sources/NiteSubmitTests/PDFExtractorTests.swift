import AppKit
import CoreText
import Foundation
import NiteSubmitCore

/// Draws the given lines as black text on white and returns a JPEG of it. This is
/// how the tests get a page that looks like a scan: PDFKit finds no text layer in
/// an image-only page, so the extractor has to fall back to Vision for it.
private func renderScanJPEG(lines: [String], width: Int = 1240, height: Int = 1754) -> Data? {
    guard let ctx = CGContext(data: nil, width: width, height: height,
                              bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
    else { return nil }
    ctx.setFillColor(CGColor(gray: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    // No CTM flip: a bitmap context already has its origin bottom-left, so
    // measuring y down from the top is enough, and flipping the matrix as well
    // renders the glyphs upside down — Vision still returns observations for
    // those, just as gibberish.
    ctx.setFillColor(CGColor(gray: 0, alpha: 1))
    for (index, text) in lines.enumerated() {
        let attributed = NSAttributedString(string: text, attributes: [
            .font: NSFont.systemFont(ofSize: 52, weight: .bold),
            .foregroundColor: NSColor.black,
        ])
        ctx.textPosition = CGPoint(x: 90, y: CGFloat(height) - 160 - CGFloat(index) * 130)
        CTLineDraw(CTLineCreateWithAttributedString(attributed), ctx)
    }
    guard let image = ctx.makeImage() else { return nil }
    return NSBitmapImageRep(cgImage: image).representation(using: .jpeg, properties: [:])
}

/// Writes a two-page PDF by hand: page 1 carries a real text layer, page 2 carries
/// nothing but the scan image. This is the submission shape that used to lose its
/// identity fields, because the document had text on page 1 and so skipped OCR.
private func makeMixedScanPDF(scanLines: [String], typedLines: [String]) -> Data? {
    guard let jpeg = renderScanJPEG(lines: scanLines) else { return nil }

    func escape(_ s: String) -> String {
        s.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "(", with: "\\(")
            .replacingOccurrences(of: ")", with: "\\)")
    }
    let typedContent = "BT /F1 26 Tf 60 760 Td 30 TL\n"
        + typedLines.map { "(\(escape($0))) Tj T*" }.joined(separator: "\n")
        + "\nET"
    let imageContent = "q 595 0 0 842 0 0 cm /Im0 Do Q"

    // Object numbers: 1 catalog, 2 page tree, 3 page 1, 4 its content, 5 font,
    // 6 page 2, 7 the scan, 8 its content. Assembled as bytes rather than as a
    // String so the JPEG stream lands in the file exactly as it came out of the
    // encoder — round-tripping binary through String corrupts it.
    let objects: [Int: String] = [
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 /MediaBox [0 0 595 842] >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        4: "<< /Length \(typedContent.utf8.count) >>\nstream\n\(typedContent)\nendstream",
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        6: "<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im0 7 0 R >> >> /Contents 8 0 R >>",
        8: "<< /Length \(imageContent.utf8.count) >>\nstream\n\(imageContent)\nendstream",
    ]
    var pdf = Data()
    var offsets: [Int: Int] = [:]
    func append(_ text: String) { pdf.append(contentsOf: Array(text.utf8)) }
    append("%PDF-1.4\n")
    for number in objects.keys.sorted() {
        offsets[number] = pdf.count
        append("\(number) 0 obj\n\(objects[number]!)\nendobj\n")
    }
    offsets[7] = pdf.count
    append("7 0 obj\n<< /Type /XObject /Subtype /Image /Width 1240 /Height 1754 "
        + "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
        + "/Length \(jpeg.count) >>\nstream\n")
    pdf.append(jpeg)
    append("\nendstream\nendobj\n")

    let xrefStart = pdf.count
    append("xref\n0 9\n0000000000 65535 f \n")
    for number in 1...8 {
        append(String(format: "%010d 00000 n \n", offsets[number] ?? 0))
    }
    append("trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n\(xrefStart)\n%%EOF\n")
    return pdf
}

private func corpusPDF() -> URL? {
    try? FileManager.default.contentsOfDirectory(
        at: URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/corpus/pdf"),
        includingPropertiesForKeys: nil
    ).first { $0.pathExtension == "pdf" }
}

func runPDFExtractorTests() {
    suite("PDFExtractor") {
        let fm = FileManager.default
        let tmp = fm.temporaryDirectory.appendingPathComponent("nite_extract_\(UUID().uuidString)")
        try fm.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tmp) }

        // The per-page character budget has to bound the characters, not just the
        // number of lines. The old code took the first maxCharactersPerPage/40
        // lines of the fully materialised page, so four 80-character lines under a
        // 120-character budget came back as 240 characters.
        scenario("a page longer than the character budget is cut before line splitting") {
            guard let corpus = corpusPDF() else {
                check(false, "no corpus PDF available for the extraction tests")
                return
            }
            let longLines = (0..<6).map { "Candidate number 0048\(12) is a deliberately long line of text \($0)" }
            guard let pdf = makeMixedScanPDF(scanLines: ["Student Name: Jane Doe"],
                                             typedLines: longLines) else {
                check(false, "could not build the generated PDF")
                return
            }
            let url = tmp.appendingPathComponent("long_text_layer.pdf")
            try pdf.write(to: url)
            let tight = PDFExtractor(maxCharactersPerPage: 120)
            guard case .success(let doc) = try tight.extract(at: url) else {
                check(false, "generated PDF did not extract")
                return
            }
            for page in doc.pages {
                let chars = page.lines.reduce(0) { $0 + $1.count }
                check(chars <= 120,
                      "page \(page.pageNumber) is cut to the 120-character budget (got \(chars))")
            }
            // The same file read with the shipping budget keeps all of its text.
            guard case .success(let full) = try PDFExtractor().extract(at: url) else {
                check(false, "generated PDF did not extract at the default budget")
                return
            }
            eq(full.pages.first?.lines.count ?? 0, longLines.count,
               "the default budget keeps every line of a normal-length page")
            _ = corpus
        }

        // Identity fields printed on a scanned page behind a typed cover sheet are
        // the whole point of a submission filename, and they were dropped because
        // the document had a text layer on page 1 and so skipped OCR entirely.
        scenario("a scan behind a typed cover sheet is OCR'd and merged in") {
            let scanLines = [
                "Student Name: Jane Doe",
                "Student Number: 12345678",
                "Module Code: UFMXYZ-30-3",
            ]
            guard let pdf = makeMixedScanPDF(scanLines: scanLines,
                                             typedLines: ["University of the West of England"]) else {
                check(false, "could not build the generated mixed PDF")
                return
            }
            let url = tmp.appendingPathComponent("typed_cover_and_scan.pdf")
            try pdf.write(to: url)
            guard case .success(let doc) = try PDFExtractor().extract(at: url) else {
                check(false, "mixed PDF did not extract at all")
                return
            }
            eq(doc.pageCount, 2, "the mixed PDF reports both pages")
            check(doc.textOrigin == .ocr,
                  "a document containing recognised text is marked as OCR origin")
            check(!doc.pages[0].lines.isEmpty, "the typed cover page keeps its text layer")
            let scanned = doc.pages.first { $0.pageNumber == 2 }
            let scannedText = (scanned?.lines ?? []).joined(separator: " ")
            check(!scannedText.isEmpty,
                  "the scanned page contributes recognised text instead of being skipped")
            if scannedText.isEmpty {
                // No OCR backend available on this machine (headless CI, no Vision
                // model). Report it rather than pretending the check passed.
                check(true, "no OCR backend available here — recognised-text check skipped")
            } else {
                check(scannedText.localizedCaseInsensitiveContains("Jane")
                      && scannedText.localizedCaseInsensitiveContains("Doe"),
                      "the identity block on the scanned page is read back (\"\(scannedText.prefix(60))\")")
            }
            // The merged document is what the filename is built from, so the field
            // the scan carried has to reach the detector.
            let detected = FieldDetector().detect(in: doc)
            check(!detected.studentId.isMissing,
                  "the student number on the scanned page is not dropped")
        }
    }
}
