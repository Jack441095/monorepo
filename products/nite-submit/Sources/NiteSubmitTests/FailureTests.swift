import Foundation
import NiteSubmitCore

func runFailureCaseTests(_ dir: URL) {
    suite("Failure handling") {
        // A PDF that draws no text must be reported as image-only so the app
        // offers OCR or manual entry. Asserting the outcome is the point:
        // swallowing the result here passed whether or not extraction worked.
        scenario("a text-free PDF is reported as image-only") {
            let minimal = """
            %PDF-1.4
            1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
            2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
            3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
            trailer<</Size 4/Root 1 0 R>>
            %%EOF
            """.data(using: .utf8)!
            let url = dir.appendingPathComponent("_image_only_test.pdf")
            try minimal.write(to: url)
            defer { try? FileManager.default.removeItem(at: url) }
            switch try PDFExtractor().extract(at: url) {
            case .imageOnly(let pageCount):
                eq(pageCount, 1, "image-only outcome reports the page count it saw")
            case .success:
                check(false, "a PDF with no text layer is reported as image-only, not as usable text")
            }
        }
        scenario("a malformed PDF gives a friendly domain error") {
            let url = dir.appendingPathComponent("_garbage_test.pdf")
            try Data("this is not a pdf at all".utf8).write(to: url)
            defer { try? FileManager.default.removeItem(at: url) }
            var friendlyError = false
            do { _ = try PDFExtractor().extract(at: url) } catch {
                friendlyError = error is PDFExtractError
            }
            check(friendlyError, "malformed PDF gives friendly domain error")
        }
        scenario("a zero-byte PDF errors gracefully") {
            let url = dir.appendingPathComponent("_zero_test.pdf")
            try Data().write(to: url)
            defer { try? FileManager.default.removeItem(at: url) }
            throwsError(try PDFExtractor().extract(at: url), "zero-byte PDF errors gracefully")
        }
        scenario("a missing file errors cleanly") {
            let ghost = dir.appendingPathComponent("_does_not_exist.pdf")
            throwsError(try PDFExtractor().extract(at: ghost), "missing file errors cleanly")
        }
    }
}
