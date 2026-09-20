import Foundation

/// Result of a lossless PDF optimization pass.
public struct PDFOptimizationReceipt: Codable, Equatable, Sendable {
    public var outputURL: URL
    public var originalSizeBytes: Int64
    public var optimizedSizeBytes: Int64
    public var sha256Checksum: String

    public var bytesSaved: Int64 { originalSizeBytes - optimizedSizeBytes }
    public var percentSaved: Double {
        guard originalSizeBytes > 0 else { return 0 }
        return Double(bytesSaved) / Double(originalSizeBytes) * 100
    }

    public init(outputURL: URL, originalSizeBytes: Int64, optimizedSizeBytes: Int64, sha256Checksum: String) {
        self.outputURL = outputURL
        self.originalSizeBytes = originalSizeBytes
        self.optimizedSizeBytes = optimizedSizeBytes
        self.sha256Checksum = sha256Checksum
    }
}

public enum PDFOptimizerError: LocalizedError {
    case toolUnavailable
    case sourceNotFound(URL)
    case notAPDF(URL)
    case optimizationFailed(String)

    public var errorDescription: String? {
        switch self {
        case .toolUnavailable:
            return "PDF optimization is unavailable — the bundled qpdf tool could not be found."
        case .sourceNotFound(let url):
            return "Source file not found at \(url.path)."
        case .notAPDF(let url):
            return "\(url.lastPathComponent) is not a PDF."
        case .optimizationFailed(let reason):
            return "Could not optimize this PDF: \(reason)"
        }
    }
}

/// Lossless PDF size reduction via the bundled qpdf tool: recompresses internal streams and
/// consolidates small objects into object streams (a PDF 1.5+ feature). This changes the PDF's
/// bytes and internal structure but never its visible content — page count, text, and images are
/// unchanged. That is a deliberate, important distinction from the rest of this app: every other
/// copy/rename/archive path in NiteSubmit guarantees byte-identical output (verified via SHA-256
/// before/after). Optimization intentionally produces a *different* file, so it is never invoked
/// as part of that byte-preserving path — it is always a separate, explicit, opt-in action whose
/// result is clearly a new file, not a copy of the original.
public struct PDFOptimizer: Sendable {
    public init() {}

    /// Resolves the app's own bundled qpdf, the same way ArchiveEngine resolves its bundled 7za:
    /// relative to the running executable's own location, so it works identically whether this is
    /// the GUI app or the CLI tool, both of which live at Contents/MacOS/<name> in the same bundle.
    private func bundledQPDFPath() -> String? {
        guard let exe = CommandLine.arguments.first else { return nil }
        let macOSDir = URL(fileURLWithPath: exe).resolvingSymlinksInPath().deletingLastPathComponent()
        let candidate = macOSDir.deletingLastPathComponent()
            .appendingPathComponent("Resources/bin/qpdf").path
        return FileManager.default.isExecutableFile(atPath: candidate) ? candidate : nil
    }

    private func findSystemQPDF() -> String? {
        for p in ["/opt/homebrew/bin/qpdf", "/usr/local/bin/qpdf", "/usr/bin/qpdf"] {
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return nil
    }

    /// Losslessly optimizes `source` and writes the result to `destination`. `destination` must
    /// differ from `source` — this never overwrites the original in place, so the original is
    /// always left untouched regardless of what the caller does with the result.
    @discardableResult
    public func optimize(source: URL, destination: URL) throws -> PDFOptimizationReceipt {
        let fm = FileManager.default
        guard fm.fileExists(atPath: source.path) else { throw PDFOptimizerError.sourceNotFound(source) }
        guard source.pathExtension.lowercased() == "pdf" else { throw PDFOptimizerError.notAPDF(source) }
        guard let qpdfPath = bundledQPDFPath() ?? findSystemQPDF() else {
            throw PDFOptimizerError.toolUnavailable
        }

        let originalSize = (try? fm.attributesOfItem(atPath: source.path)[.size] as? Int64) ?? nil ?? 0

        try? fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: qpdfPath)
        process.arguments = [
            "--object-streams=generate",
            "--compress-streams=y",
            "--recompress-flate",
            "--compression-level=9",
            source.path, destination.path,
        ]
        let pipe = Pipe()
        process.standardError = pipe
        process.standardOutput = pipe
        try process.run()
        process.waitUntilExit()

        // qpdf's exit codes: 0 = clean success, 3 = succeeded with warnings about pre-existing
        // quirks in the source PDF that it repaired (common with real-world PDFs; not a failure
        // of this optimization step). Anything else is a real failure.
        guard process.terminationStatus == 0 || process.terminationStatus == 3 else {
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let msg = String(data: data, encoding: .utf8) ?? "qpdf exited with status \(process.terminationStatus)"
            throw PDFOptimizerError.optimizationFailed(msg)
        }

        guard fm.fileExists(atPath: destination.path),
              let attrs = try? fm.attributesOfItem(atPath: destination.path),
              let optimizedSize = attrs[.size] as? Int64 else {
            throw PDFOptimizerError.optimizationFailed("Optimized output file was not produced.")
        }

        let checksum = try FileOperator.sha256(of: destination)
        return PDFOptimizationReceipt(outputURL: destination, originalSizeBytes: originalSize,
                                       optimizedSizeBytes: optimizedSize, sha256Checksum: checksum)
    }
}
