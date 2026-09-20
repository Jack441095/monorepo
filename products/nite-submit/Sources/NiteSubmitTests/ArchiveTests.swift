import Foundation
import NiteSubmitCore

/// Whether a real 7z/7za tool is installed — it is not bundled with the app or with macOS, so
/// tests must not assume it's present (a typical customer Mac won't have it either).
private func realSevenZipToolAvailable() -> Bool {
    let fm = FileManager.default
    for name in ["7z", "7za"] {
        for dir in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"] {
            if fm.isExecutableFile(atPath: "\(dir)/\(name)") { return true }
        }
    }
    return false
}

public func runArchiveTests() {
    suite("ArchiveEngine & MediaExtractor") {
        let fm = FileManager.default
        let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_submit_archive_test_\(UUID().uuidString)")
        try? fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tempDir) }

        // Prepare dummy test files (.wav, .mp4, .pdf)
        let file1 = tempDir.appendingPathComponent("1048291_Audio_Stem.wav")
        let file2 = tempDir.appendingPathComponent("MOD402_Video_Demo.mp4")
        let file3 = tempDir.appendingPathComponent("Assignment_Report.pdf")

        let subFolder = tempDir.appendingPathComponent("Submission_Assets", isDirectory: true)
        try? fm.createDirectory(at: subFolder, withIntermediateDirectories: true)
        let innerFile = subFolder.appendingPathComponent("ReadMe.txt")
        try? "Project documentation".data(using: .utf8)?.write(to: innerFile)

        try? "RIFF_WAV_HEADER_DATA_DUMMY".data(using: .utf8)?.write(to: file1)
        try? "FTYP_MP4_ATOM_DATA_DUMMY".data(using: .utf8)?.write(to: file2)
        try? "%PDF-1.4_HEADER_DUMMY".data(using: .utf8)?.write(to: file3)

        // 1. Test 7z Compression. Without the real 7z tool installed (not bundled with the app or
        // macOS — most customer Macs won't have it), ArchiveEngine must fall back to a real ZIP
        // rather than silently mislabeling one as ".7z"; the receipt's format/URL reflect
        // whichever actually happened, and the file at that URL must actually exist with a
        // matching extension.
        let archive7z = tempDir.appendingPathComponent("2026_MOD402_1048291_Submission.7z")
        do {
            let receipt = try ArchiveEngine().compress(sources: [file1, file2, file3, subFolder],
                                                       destinationArchive: archive7z,
                                                       format: .sevenZip,
                                                       level: .maximum)
            check(fm.fileExists(atPath: receipt.archiveURL.path), "7z archive output exists")
            check(receipt.archiveURL.pathExtension == receipt.format.fileExtension,
                  "archive extension matches its actual format (\(receipt.archiveURL.pathExtension) vs \(receipt.format.fileExtension))")
            if realSevenZipToolAvailable() {
                check(receipt.format == .sevenZip, "real 7z tool available: output is genuine 7z")
            } else {
                check(receipt.format == .zip, "7z tool unavailable: falls back to a real ZIP, not a mislabeled .7z")
            }
            check(receipt.sourceCount == 4, "7z source count matches including folder")
            check(!receipt.sha256Checksum.isEmpty, "7z sha256 checksum generated")
        } catch {
            check(false, "7z compression error: \(error)")
        }

        // 2. Test Password-Encrypted ZIP Compression
        let archiveZip = tempDir.appendingPathComponent("2026_MOD402_1048291_Encrypted.zip")
        do {
            let receipt = try ArchiveEngine().compress(sources: [file1, file2, file3],
                                                       destinationArchive: archiveZip,
                                                       format: .zip,
                                                       level: .normal,
                                                       password: "NiteSubmitPassword2026")
            check(fm.fileExists(atPath: archiveZip.path), "Encrypted ZIP archive output exists")
            check(receipt.isEncrypted, "Receipt marks encrypted zip archive")
            check(receipt.archiveSizeBytes > 0, "ZIP archive size > 0")
        } catch {
            check(false, "Encrypted ZIP compression error: \(error)")
        }

        // 3. Test TAR.GZ Compression
        let archiveTar = tempDir.appendingPathComponent("2026_MOD402_1048291_Submission.tar.gz")
        do {
            let receipt = try ArchiveEngine().compress(sources: [file1, file2, file3],
                                                       destinationArchive: archiveTar,
                                                       format: .tarGz,
                                                       level: .fast)
            check(fm.fileExists(atPath: archiveTar.path), "TAR.GZ archive output exists")
            check(receipt.archiveSizeBytes > 0, "TAR.GZ size > 0")
        } catch {
            check(false, "TAR.GZ compression error: \(error)")
        }

        // 4. Test Volume Split Setting. Volume splitting is a 7z-specific feature with no honest
        // ZIP/ditto equivalent, so without the real 7z tool this must fail loudly
        // (.sevenZipToolRequired) rather than silently produce an unsplit archive that still
        // claims isSplitVolume — a caller relying on the split for delivery-size limits needs to
        // know it didn't happen, not get a false success.
        let archiveSplit = tempDir.appendingPathComponent("2026_MOD402_1048291_Split.7z")
        do {
            let receipt = try ArchiveEngine().compress(sources: [file1, file2],
                                                       destinationArchive: archiveSplit,
                                                       format: .sevenZip,
                                                       level: .normal,
                                                       volumeSplit: .mb25)
            check(realSevenZipToolAvailable(), "volume split only succeeds when the real 7z tool is present")
            check(receipt.isSplitVolume, "Receipt marks split volume request")
        } catch ArchiveEngineError.sevenZipToolRequired {
            check(!realSevenZipToolAvailable(), "volume split correctly refused without the real 7z tool")
        } catch {
            check(false, "Volume split compression error: \(error)")
        }

        // 5. Test MediaExtractor filename & format detection
        let wavMetadata = MediaExtractor().extractMetadata(at: file1)
        check(wavMetadata.studentId.value == "1048291", "Extracted student ID from .wav filename")

        let mp4Metadata = MediaExtractor().extractMetadata(at: file2)
        check(mp4Metadata.moduleCode.value == "MOD402", "Extracted module code from .mp4 filename")

        // 6. Test Error Handling (No Sources)
        do {
            _ = try ArchiveEngine().compress(sources: [], destinationArchive: archiveZip)
            check(false, "Expected ArchiveEngineError.noSources")
        } catch ArchiveEngineError.noSources {
            check(true, "Correctly threw noSources error")
        } catch {
            check(false, "Unexpected error type: \(error)")
        }
    }
}
