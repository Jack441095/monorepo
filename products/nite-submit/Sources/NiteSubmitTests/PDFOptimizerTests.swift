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
        let fm = FileManager.default
        let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_submit_pdfopt_test_\(UUID().uuidString)")
        try fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tempDir) }

        // A source we cannot measure must never come back as a receipt claiming a
        // 0-byte original. The old code coerced the failed stat to 0, so the
        // receipt divided by zero into a flat "0% saved" for a real submission and
        // hid the permission problem behind a number that looked like a result.
        scenario("a source we cannot measure is refused, not counted as 0 bytes") {
            let locked = fm.temporaryDirectory.appendingPathComponent("nite_opt_locked_\(UUID().uuidString)")
            try fm.createDirectory(at: locked, withIntermediateDirectories: true)
            defer {
                try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: locked.path)
                try? fm.removeItem(at: locked)
            }
            let source = locked.appendingPathComponent("unreadable.pdf")
            try Data("%PDF-1.4".utf8).write(to: source)
            let output = tempDir.appendingPathComponent("out_stat.pdf")
            try fm.setAttributes([.posixPermissions: 0o000], ofItemAtPath: locked.path)
            do {
                let receipt = try PDFOptimizer().optimize(source: source, destination: output)
                check(false, "expected a failure, got a receipt claiming \(receipt.originalSizeBytes) bytes")
            } catch PDFOptimizerError.sourceUnreadable {
                check(true, "a source we cannot stat throws sourceUnreadable")
            } catch PDFOptimizerError.sourceNotFound {
                // A folder with no search permission hides the file from stat as
                // well, so the file is refused before it is ever measured. Either
                // way the call fails instead of inventing a zero-byte original.
                check(true, "a source behind an unreadable folder is refused before it is measured")
            } catch {
                check(false, "wrong error for an unmeasurable source: \(error)")
            }
            check(!fm.fileExists(atPath: output.path),
                  "no optimized file is produced for a source we cannot read")
        }

        guard realQPDFAvailable() else {
            check(true, "qpdf not installed on this machine — skipping (packaged .app bundles its own copy; see tools/bin/qpdf)")
            return
        }

        let corpusDir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().appendingPathComponent("Fixtures/corpus/pdf")
        guard let source = try? fm.contentsOfDirectory(at: corpusDir, includingPropertiesForKeys: nil)
            .first(where: { $0.pathExtension == "pdf" }) else {
            check(false, "no corpus PDF fixture found to optimize")
            return
        }

        let sourceBytesBefore = try? Data(contentsOf: source)
        let sourceHashBefore = try? sha256(source)
        let destination = tempDir.appendingPathComponent("optimized.pdf")

        do {
            let receipt = try PDFOptimizer().optimize(source: source, destination: destination)
            check(fm.fileExists(atPath: destination.path), "optimized output file exists")
            check(receipt.optimizedSizeBytes > 0, "optimized output is non-empty")
            check(!receipt.sha256Checksum.isEmpty, "optimized output has a checksum")

            let sourceBytesAfter = try? Data(contentsOf: source)
            check(sourceBytesBefore == sourceBytesAfter, "source file is never modified by optimization")
            check(try sha256(source) == sourceHashBefore,
                  "the source keeps the same SHA-256 after optimization")
            check(receipt.originalSizeBytes == (sourceBytesBefore?.count).map(Int64.init) ?? -1,
                  "the receipt measures the real original size, not a placeholder")

            if let sourceDoc = PDFDocumentText(url: source), let outDoc = PDFDocumentText(url: destination) {
                check(sourceDoc.pageCount == outDoc.pageCount, "optimized output has the same page count")
                check(sourceDoc.allText == outDoc.allText, "optimized output has identical visible text (lossless)")
            } else {
                check(false, "could not read back source/output PDFs to compare content")
            }
        } catch {
            check(false, "optimize(source:destination:) failed: \(error)")
        }

        // The previous version deleted the destination before qpdf ran, so a qpdf
        // failure left the student with nothing at all. qpdf now writes into a
        // hidden sibling and the swap-in is the last step.
        scenario("a failing optimize leaves the previous destination in place") {
            let keepDir = fm.temporaryDirectory.appendingPathComponent("nite_opt_keep_\(UUID().uuidString)")
            try fm.createDirectory(at: keepDir, withIntermediateDirectories: true)
            defer { try? fm.removeItem(at: keepDir) }
            let existing = keepDir.appendingPathComponent("previous.pdf")
            try Data("PREVIOUS-OPTIMISED-FILE".utf8).write(to: existing)
            // qpdf rejects this outright (exit status 2), so the run fails after
            // it has already been given an output path.
            let broken = keepDir.appendingPathComponent("broken.pdf")
            try Data("this is not a PDF at all, not even close".utf8).write(to: broken)
            throwsError(try PDFOptimizer().optimize(source: broken, destination: existing),
                        "a qpdf failure is reported to the caller")
            eq(String(decoding: try Data(contentsOf: existing), as: UTF8.self),
               "PREVIOUS-OPTIMISED-FILE",
               "the destination still holds the file that was there before")
            let leftovers = (try? fm.contentsOfDirectory(atPath: keepDir.path)) ?? []
            check(!leftovers.contains { $0.hasPrefix(".nitesubmit-optimize-") },
                  "no staging file is left in the destination folder")
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
