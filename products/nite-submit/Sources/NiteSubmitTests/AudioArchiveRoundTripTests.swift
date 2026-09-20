import Foundation
import NiteSubmitCore

/// Whether a real 7z tool is available for this test run — mirrors the same helper pattern used
/// in ArchiveTests.swift. Not bundled with the debug/test binaries (only the packaged .app has
/// it); installed via Homebrew on this dev machine for testing.
private func realSevenZipAvailableForRoundTrip() -> Bool {
    let fm = FileManager.default
    for name in ["7z", "7za"] {
        for dir in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"] {
            if fm.isExecutableFile(atPath: "\(dir)/\(name)") { return true }
        }
    }
    return false
}

/// Writes a minimal, valid 16-bit PCM stereo WAV file with deterministic pseudo-random sample
/// data — realistic enough (not silence, not a pure tone) to exercise real compression the way
/// an actual audio stem upload would, without needing any audio library.
private func writeSyntheticWAV(to url: URL, seconds: Int = 5, sampleRate: Int = 44100) throws {
    let channels = 2
    let bitsPerSample = 16
    let byteRate = sampleRate * channels * bitsPerSample / 8
    let blockAlign = channels * bitsPerSample / 8
    let sampleCount = sampleRate * seconds
    let dataSize = sampleCount * blockAlign

    var data = Data()
    func appendString(_ s: String) { data.append(s.data(using: .ascii)!) }
    func appendUInt32(_ v: UInt32) { withUnsafeBytes(of: v.littleEndian) { data.append(contentsOf: $0) } }
    func appendUInt16(_ v: UInt16) { withUnsafeBytes(of: v.littleEndian) { data.append(contentsOf: $0) } }

    appendString("RIFF")
    appendUInt32(UInt32(36 + dataSize))
    appendString("WAVE")
    appendString("fmt ")
    appendUInt32(16)
    appendUInt16(1) // PCM
    appendUInt16(UInt16(channels))
    appendUInt32(UInt32(sampleRate))
    appendUInt32(UInt32(byteRate))
    appendUInt16(UInt16(blockAlign))
    appendUInt16(UInt16(bitsPerSample))
    appendString("data")
    appendUInt32(UInt32(dataSize))

    // Deterministic pseudo-random-ish PCM: layered sine components plus an LCG-driven noise
    // floor, per channel — structured enough to resemble a real mixed stem, not silence.
    var lcg: UInt64 = 0x2545F4914F6CDD1D
    func nextNoise() -> Double {
        lcg = 6364136223846793005 &* lcg &+ 1442695040888963407
        return (Double(lcg >> 40) / Double(1 << 24)) - 0.5
    }
    for i in 0..<sampleCount {
        let t = Double(i) / Double(sampleRate)
        let left = 0.25 * sin(2 * .pi * 220 * t) + 0.1 * sin(2 * .pi * 440 * t) + 0.05 * nextNoise()
        let right = 0.25 * sin(2 * .pi * 220 * t + 0.1) + 0.1 * sin(2 * .pi * 660 * t) + 0.05 * nextNoise()
        appendUInt16(UInt16(bitPattern: Int16(max(-32767, min(32767, left * 32767)))))
        appendUInt16(UInt16(bitPattern: Int16(max(-32767, min(32767, right * 32767)))))
    }

    try data.write(to: url)
}

/// Extracts a single archive back to a directory using the same real tools the app bundles
/// (7za for .7z; /usr/bin/unzip, present on every Mac, for .zip) — exercising exactly what a
/// real recipient double-clicking the archive would get.
private func extractArchive(_ archiveURL: URL, format: ArchiveFormat, to destDir: URL) throws {
    try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
    let process = Process()
    switch format {
    case .sevenZip:
        for candidate in ["/opt/homebrew/bin/7z", "/usr/local/bin/7z", "/opt/homebrew/bin/7za", "/usr/local/bin/7za"] {
            if FileManager.default.isExecutableFile(atPath: candidate) {
                process.executableURL = URL(fileURLWithPath: candidate)
                break
            }
        }
        process.arguments = ["x", archiveURL.path, "-o\(destDir.path)", "-y"]
    case .zip:
        process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        process.arguments = ["-o", archiveURL.path, "-d", destDir.path]
    case .tarGz:
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        process.arguments = ["-xzf", archiveURL.path, "-C", destDir.path]
    }
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        throw NSError(domain: "extractArchive", code: Int(process.terminationStatus),
                      userInfo: [NSLocalizedDescriptionKey: out])
    }
}

/// Archives `sourceFile` under a fresh copy named `stagedName` (so extraction always yields a
/// predictable path to check), for each of `formats`, extracts it back with the real bundled/
/// system tool, and verifies the result is byte-identical to the original — the core "does
/// anything corrupt" guarantee this whole suite exists to protect.
private func checkRoundTrip(label: String, sourceFile: URL, stagedName: String, formats: [ArchiveFormat]) {
    let fm = FileManager.default
    let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_submit_roundtrip_\(UUID().uuidString)")
    try? fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? fm.removeItem(at: tempDir) }

    let stagedSource = tempDir.appendingPathComponent(stagedName)
    guard (try? fm.copyItem(at: sourceFile, to: stagedSource)) != nil,
          let originalBytes = try? Data(contentsOf: stagedSource) else {
        check(false, "\(label): could not stage source fixture from \(sourceFile.path)")
        return
    }

    for format in formats {
        let archiveURL = tempDir.appendingPathComponent("\(stagedName)_\(format.rawValue).\(format.fileExtension)")
        do {
            let receipt = try ArchiveEngine().compress(sources: [stagedSource], destinationArchive: archiveURL,
                                                        format: format, level: .maximum)
            check(fm.fileExists(atPath: receipt.archiveURL.path), "\(label) [\(format.rawValue)]: archive was created")

            let extractDir = tempDir.appendingPathComponent("extracted_\(format.rawValue)")
            try extractArchive(receipt.archiveURL, format: format, to: extractDir)

            let extractedFile = extractDir.appendingPathComponent(stagedName)
            guard let extractedBytes = try? Data(contentsOf: extractedFile) else {
                check(false, "\(label) [\(format.rawValue)]: extracted file not found after extraction")
                continue
            }
            check(extractedBytes == originalBytes, "\(label) [\(format.rawValue)]: extracted file is byte-identical to the original — no corruption")

            let pct = (1 - Double(receipt.archiveSizeBytes) / Double(originalBytes.count)) * 100
            print("   \(label) [\(format.rawValue)]: \(originalBytes.count) bytes -> \(receipt.archiveSizeBytes) bytes (\(String(format: "%.1f", pct))% smaller)")
        } catch {
            check(false, "\(label) [\(format.rawValue)] round trip failed: \(error)")
        }
    }
}

private func roundTripFixturesDir() -> URL {
    URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures/archive_roundtrip")
}

public func runAudioArchiveRoundTripTests() {
    suite("Archive round trip (corruption check)") {
        guard realSevenZipAvailableForRoundTrip() else {
            check(true, "7z tool not installed on this machine — skipping (packaged .app bundles its own copy)")
            return
        }

        // Synthetic WAV, generated fresh each run (deterministic content, realistic PCM entropy).
        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("nite_submit_wav_gen_\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }
        let wavURL = tempDir.appendingPathComponent("stem_test.wav")
        do {
            try writeSyntheticWAV(to: wavURL, seconds: 8)
            checkRoundTrip(label: "WAV", sourceFile: wavURL, stagedName: "stem_test.wav", formats: [.sevenZip, .zip])
        } catch {
            check(false, "could not generate synthetic WAV fixture: \(error)")
        }

        // Real fixtures checked into the repo — genuine H.264/AAC MP4 and a genuine OOXML DOCX,
        // not synthetic stand-ins, so this exercises real-world already-compressed / zip-in-zip
        // content the same way the WAV case exercises raw PCM.
        let fixtures = roundTripFixturesDir()
        let mp4 = fixtures.appendingPathComponent("demo_clip.mp4")
        if FileManager.default.fileExists(atPath: mp4.path) {
            checkRoundTrip(label: "MP4", sourceFile: mp4, stagedName: "demo_clip.mp4", formats: [.sevenZip, .zip])
        } else {
            check(false, "MP4 fixture missing at \(mp4.path)")
        }

        let docx = fixtures.appendingPathComponent("assignment_report.docx")
        if FileManager.default.fileExists(atPath: docx.path) {
            checkRoundTrip(label: "DOCX", sourceFile: docx, stagedName: "assignment_report.docx", formats: [.sevenZip, .zip])
        } else {
            check(false, "DOCX fixture missing at \(docx.path)")
        }
    }
}
