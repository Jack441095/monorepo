import Foundation
import NiteSubmitCore

/// Whether a real qpdf is available — it is not bundled with the debug/test binaries built by
/// `swift build`/`swift test` (only the packaged .app bundles it), so tests must not assume it's
/// present. On this dev machine it's installed via Homebrew for testing; a real customer's Mac
/// gets it from the app bundle instead (see PDFOptimizer.bundledQPDFPath()).
private func realQPDFAvailable() -> Bool {
    let fm = FileManager.default
    for dir in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"] {
        if fm.isExecutableFile(atPath: "\(dir)/qpdf") { return true }
    }
    return false
}

public func runPDFOptimizerTests() {
    suite("PDFOptimizer") {
        guard realQPDFAvailable() else {
            check(true, "qpdf not installed on this machine — skipping (packaged .app bundles its own copy; see tools/bin/qpdf)")
            return
        }

        let fm = FileManager.default
        let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_submit_pdfopt_test_\(UUID().uuidString)")
        try? fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tempDir) }

        let corpusDir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().appendingPathComponent("Fixtures/corpus/pdf")
        guard let source = try? fm.contentsOfDirectory(at: corpusDir, includingPropertiesForKeys: nil)
            .first(where: { $0.pathExtension == "pdf" }) else {
            check(false, "no corpus PDF fixture found to optimize")
            return
        }

        let sourceBytesBefore = try? Data(contentsOf: source)
        let destination = tempDir.appendingPathComponent("optimized.pdf")

        do {
            let receipt = try PDFOptimizer().optimize(source: source, destination: destination)
            check(fm.fileExists(atPath: destination.path), "optimized output file exists")
            check(receipt.optimizedSizeBytes > 0, "optimized output is non-empty")
            check(!receipt.sha256Checksum.isEmpty, "optimized output has a checksum")

            let sourceBytesAfter = try? Data(contentsOf: source)
            check(sourceBytesBefore == sourceBytesAfter, "source file is never modified by optimization")

            if let sourceDoc = PDFDocumentText(url: source), let outDoc = PDFDocumentText(url: destination) {
                check(sourceDoc.pageCount == outDoc.pageCount, "optimized output has the same page count")
                check(sourceDoc.allText == outDoc.allText, "optimized output has identical visible text (lossless)")
            } else {
                check(false, "could not read back source/output PDFs to compare content")
            }
        } catch {
            check(false, "optimize(source:destination:) failed: \(error)")
        }

        // Error paths
        do {
            _ = try PDFOptimizer().optimize(source: tempDir.appendingPathComponent("missing.pdf"),
                                             destination: tempDir.appendingPathComponent("out.pdf"))
            check(false, "expected PDFOptimizerError.sourceNotFound")
        } catch PDFOptimizerError.sourceNotFound { check(true, "missing source throws sourceNotFound") }
        catch { check(false, "wrong error for missing source: \(error)") }

        let notAPDF = tempDir.appendingPathComponent("not_a_pdf.txt")
        try? "hello".data(using: .utf8)?.write(to: notAPDF)
        do {
            _ = try PDFOptimizer().optimize(source: notAPDF, destination: tempDir.appendingPathComponent("out2.pdf"))
            check(false, "expected PDFOptimizerError.notAPDF")
        } catch PDFOptimizerError.notAPDF { check(true, "non-PDF source throws notAPDF") }
        catch { check(false, "wrong error for non-PDF source: \(error)") }
    }
}

/// Minimal text/page-count reader used only to compare source vs. optimized output — reuses
/// PDFExtractor (the app's own PDFKit wrapper) rather than adding a second way to read a PDF.
private struct PDFDocumentText {
    let pageCount: Int
    let allText: String

    init?(url: URL) {
        guard case .success(let doc) = try? PDFExtractor().extract(at: url) else { return nil }
        pageCount = doc.pageCount
        allText = doc.pages.map { $0.lines.joined(separator: "\n") }.joined()
    }
}
