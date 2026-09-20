import Foundation
import CommonCrypto

/// Supported submission archive formats.
public enum ArchiveFormat: String, Codable, CaseIterable, Sendable {
    case sevenZip = "7z"
    case zip = "zip"
    case tarGz = "tar.gz"

    public var fileExtension: String { rawValue }
    public var displayName: String {
        switch self {
        case .sevenZip: return "7z Archive (.7z)"
        case .zip: return "ZIP Archive (.zip)"
        case .tarGz: return "Tarball (.tar.gz)"
        }
    }
}

/// Compression level presets.
public enum CompressionLevel: String, Codable, CaseIterable, Sendable {
    case store = "store"
    case fast = "fast"
    case normal = "normal"
    case maximum = "maximum"

    public var levelValue: Int {
        switch self {
        case .store: return 0
        case .fast: return 1
        case .normal: return 5
        case .maximum: return 9
        }
    }
}

/// Volume split size preset options for large media submissions.
public enum VolumeSplitOption: Int64, Codable, CaseIterable, Sendable {
    case singleFile = 0
    case mb25 = 26214400      // 25 MB
    case mb100 = 104857600    // 100 MB
    case mb500 = 524288000    // 500 MB
    case gb1 = 1073741824     // 1 GB
    case gb2 = 2147483648     // 2 GB

    public var displayName: String {
        switch self {
        case .singleFile: return "Single Archive File"
        case .mb25: return "25 MB Volumes"
        case .mb100: return "100 MB Volumes"
        case .mb500: return "500 MB Volumes"
        case .gb1: return "1 GB Volumes"
        case .gb2: return "2 GB Volumes"
        }
    }
}

/// Receipt generated after an archive operation completes successfully.
public struct ArchiveReceipt: Codable, Equatable, Sendable {
    public var archiveURL: URL
    public var format: ArchiveFormat
    public var sourceCount: Int
    public var uncompressedSizeBytes: Int64
    public var archiveSizeBytes: Int64
    public var sha256Checksum: String
    public var isEncrypted: Bool
    public var isSplitVolume: Bool
    public var createdTimestamp: Date

    public init(archiveURL: URL, format: ArchiveFormat, sourceCount: Int,
                uncompressedSizeBytes: Int64, archiveSizeBytes: Int64,
                sha256Checksum: String, isEncrypted: Bool = false,
                isSplitVolume: Bool = false, createdTimestamp: Date = Date()) {
        self.archiveURL = archiveURL
        self.format = format
        self.sourceCount = sourceCount
        self.uncompressedSizeBytes = uncompressedSizeBytes
        self.archiveSizeBytes = archiveSizeBytes
        self.sha256Checksum = sha256Checksum
        self.isEncrypted = isEncrypted
        self.isSplitVolume = isSplitVolume
        self.createdTimestamp = createdTimestamp
    }
}

public enum ArchiveEngineError: LocalizedError {
    case noSources
    case sourceNotFound(URL)
    case archiveCreationFailed(String)
    case unsupportedFormat(String)
    case sevenZipToolRequired

    public var errorDescription: String? {
        switch self {
        case .noSources: return "No input files selected for archiving."
        case .sourceNotFound(let url): return "Source file not found at \(url.path)."
        case .archiveCreationFailed(let reason): return "Could not create archive: \(reason)"
        case .unsupportedFormat(let fmt): return "Unsupported archive format: \(fmt)"
        case .sevenZipToolRequired:
            return "Password protection and volume splitting require the 7z command-line tool, which isn't installed on this Mac. Install p7zip (e.g. via Homebrew: brew install p7zip), or create the archive without a password/split."
        }
    }
}

/// Local 7z / ZIP / TAR archive compressor with zero network dependency.
public struct ArchiveEngine: Sendable {
    public init() {}

    /// Compress multiple local files or directories into a single submission archive.
    @discardableResult
    public func compress(sources: [URL],
                          destinationArchive: URL,
                          format: ArchiveFormat = .sevenZip,
                          level: CompressionLevel = .normal,
                          password: String? = nil,
                          volumeSplit: VolumeSplitOption = .singleFile) throws -> ArchiveReceipt {
        guard !sources.isEmpty else { throw ArchiveEngineError.noSources }
        let fm = FileManager.default

        var totalUncompressedSize: Int64 = 0
        for src in sources {
            guard fm.fileExists(atPath: src.path) else {
                throw ArchiveEngineError.sourceNotFound(src)
            }
            totalUncompressedSize += calculateSize(of: src)
        }

        // Ensure parent folder exists
        let parentDir = destinationArchive.deletingLastPathComponent()
        try fm.createDirectory(at: parentDir, withIntermediateDirectories: true)

        // Remove destination if it exists
        if fm.fileExists(atPath: destinationArchive.path) {
            try fm.removeItem(at: destinationArchive)
        }

        let tempDir = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tempDir) }

        // Copy/link input files into staging directory
        for src in sources {
            let target = tempDir.appendingPathComponent(src.lastPathComponent)
            if src.hasDirectoryPath {
                try fm.copyItem(at: src, to: target)
            } else {
                try fm.copyItem(at: src, to: target)
            }
        }

        let cleanPass = password?.trimmingCharacters(in: .whitespacesAndNewlines)
        let passToUse = (cleanPass != nil && !cleanPass!.isEmpty) ? cleanPass : nil

        // 7z output is only genuine 7z/LZMA2 when the real `7z`/`7za` tool is present (it is not
        // bundled with the app or with macOS). When it's missing, create7zArchive falls back to
        // `ditto`, which produces a plain ZIP — actualFormat/destinationArchive are corrected
        // below so the receipt and the file's own extension never claim ".7z" for a file that
        // isn't actually 7z-formatted.
        var actualFormat = format
        var actualDestination = destinationArchive
        switch format {
        case .sevenZip:
            let usedRealSevenZip = try create7zArchive(stagingDir: tempDir, destination: destinationArchive, level: level, password: passToUse, volumeSplit: volumeSplit)
            if !usedRealSevenZip {
                actualFormat = .zip
                actualDestination = destinationArchive.deletingPathExtension().appendingPathExtension("zip")
                try? fm.removeItem(at: actualDestination)
                try fm.moveItem(at: destinationArchive, to: actualDestination)
            }
        case .zip:
            try createZipArchive(stagingDir: tempDir, destination: destinationArchive, level: level, password: passToUse)
        case .tarGz:
            try createTarGzArchive(stagingDir: tempDir, destination: destinationArchive, level: level)
        }

        // For split volumes, the main .7z file might be named .7z.001
        var finalArchiveURL = actualDestination
        if volumeSplit != .singleFile && actualFormat == .sevenZip {
            let split001 = actualDestination.deletingPathExtension().appendingPathExtension("7z.001")
            if fm.fileExists(atPath: split001.path) {
                finalArchiveURL = split001
            }
        }

        guard fm.fileExists(atPath: finalArchiveURL.path),
              let attrs = try? fm.attributesOfItem(atPath: finalArchiveURL.path),
              let archiveSize = attrs[.size] as? Int64 else {
            throw ArchiveEngineError.archiveCreationFailed("Archive output file was not produced.")
        }

        let checksum = try computeSHA256(of: finalArchiveURL)

        return ArchiveReceipt(archiveURL: finalArchiveURL,
                               format: actualFormat,
                               sourceCount: sources.count,
                               uncompressedSizeBytes: totalUncompressedSize,
                               archiveSizeBytes: archiveSize,
                               sha256Checksum: checksum,
                               isEncrypted: actualFormat == format && passToUse != nil,
                               isSplitVolume: actualFormat == format && volumeSplit != .singleFile)
    }

    /// Returns true if the real `7z`/`7za` tool was used, false if the `ditto` ZIP fallback ran.
    /// Throws rather than silently dropping password protection or volume splitting — those are
    /// security/delivery guarantees a caller may be relying on, so failing loudly beats a silent,
    /// unencrypted, unsplit substitute that still claims success.
    @discardableResult
    private func create7zArchive(stagingDir: URL, destination: URL, level: CompressionLevel, password: String?, volumeSplit: VolumeSplitOption) throws -> Bool {
        if let p7zPath = bundledSevenZipPath() ?? findExecutable(name: "7z") ?? findExecutable(name: "7za") {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: p7zPath)
            var args = ["a", "-t7z", "-m0=lzma2", "-mx=\(level.levelValue)"]
            if let password {
                args.append("-p\(password)")
                args.append("-mhe=on") // Encrypt header/filenames
            }
            if volumeSplit != .singleFile {
                let bytes = volumeSplit.rawValue
                let mb = max(1, bytes / (1024 * 1024))
                args.append("-v\(mb)m")
            }
            args.append(destination.path)
            args.append(".")

            process.arguments = args
            process.currentDirectoryURL = stagingDir
            let pipe = Pipe()
            process.standardError = pipe
            process.standardOutput = pipe
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus == 0 { return true }
        }

        guard password == nil, volumeSplit == .singleFile else {
            throw ArchiveEngineError.sevenZipToolRequired
        }

        // Fallback: ditto (ZIP wrapper). Only reachable with no password/split requested — the
        // caller (compress(sources:...)) is responsible for correcting the reported format and
        // the output file's extension to .zip, since this did not produce a real 7z file.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-c", "-k", "--keepParent", stagingDir.path, destination.path]
        let pipe = Pipe()
        process.standardError = pipe
        process.standardOutput = pipe
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let msg = String(data: data, encoding: .utf8) ?? "ditto exited with status \(process.terminationStatus)"
            throw ArchiveEngineError.archiveCreationFailed(msg)
        }
        return false
    }

    private func createZipArchive(stagingDir: URL, destination: URL, level: CompressionLevel, password: String?) throws {
        if let password, let zipPath = findExecutable(name: "zip") {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: zipPath)
            process.arguments = ["-r", "-P", password, destination.path, "."]
            process.currentDirectoryURL = stagingDir
            let pipe = Pipe()
            process.standardError = pipe
            process.standardOutput = pipe
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus == 0 { return }
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-c", "-k", stagingDir.path, destination.path]
        let pipe = Pipe()
        process.standardError = pipe
        process.standardOutput = pipe
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let msg = String(data: data, encoding: .utf8) ?? "ditto exited with status \(process.terminationStatus)"
            throw ArchiveEngineError.archiveCreationFailed(msg)
        }
    }

    private func createTarGzArchive(stagingDir: URL, destination: URL, level: CompressionLevel) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        process.arguments = ["-czf", destination.path, "-C", stagingDir.path, "."]
        let pipe = Pipe()
        process.standardError = pipe
        process.standardOutput = pipe
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let msg = String(data: data, encoding: .utf8) ?? "tar exited with status \(process.terminationStatus)"
            throw ArchiveEngineError.archiveCreationFailed(msg)
        }
    }

    private func calculateSize(of url: URL) -> Int64 {
        let fm = FileManager.default
        var total: Int64 = 0
        if let enumerator = fm.enumerator(at: url, includingPropertiesForKeys: [.fileSizeKey], options: [.skipsHiddenFiles]) {
            for case let fileURL as URL in enumerator {
                if let resourceValues = try? fileURL.resourceValues(forKeys: [.fileSizeKey]),
                   let size = resourceValues.fileSize {
                    total += Int64(size)
                }
            }
        } else if let attrs = try? fm.attributesOfItem(atPath: url.path),
                  let size = attrs[.size] as? Int64 {
            total = size
        }
        return total
    }

    private func findExecutable(name: String) -> String? {
        let candidatePaths = ["/opt/homebrew/bin/\(name)", "/usr/local/bin/\(name)", "/usr/bin/\(name)"]
        for p in candidatePaths {
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return nil
    }

    /// The app's own bundled 7za, resolved relative to the running executable rather than via
    /// `Bundle.main` (which does not reliably resolve for a plain command-line-style executable
    /// like nitesubmit-cli, even though it lives inside the same .app bundle as the GUI). Both the
    /// GUI binary and the CLI binary sit at Contents/MacOS/<name> in the same bundle, so walking up
    /// from CommandLine.arguments[0] to Contents/Resources/bin/7za works identically for either.
    /// This is what makes real 7z/LZMA2 compression available on every customer Mac without
    /// depending on them having separately installed anything themselves.
    private func bundledSevenZipPath() -> String? {
        guard let exe = CommandLine.arguments.first else { return nil }
        let macOSDir = URL(fileURLWithPath: exe).resolvingSymlinksInPath().deletingLastPathComponent()
        let candidate = macOSDir.deletingLastPathComponent()
            .appendingPathComponent("Resources/bin/7za").path
        return FileManager.default.isExecutableFile(atPath: candidate) ? candidate : nil
    }

    private func computeSHA256(of fileURL: URL) throws -> String {
        let data = try Data(contentsOf: fileURL)
        var hash = [UInt8](repeating: 0, count: 32)
        data.withUnsafeBytes { buffer in
            _ = CC_SHA256(buffer.baseAddress, CC_LONG(buffer.count), &hash)
        }
        return hash.map { String(format: "%02x", $0) }.joined()
    }
}
