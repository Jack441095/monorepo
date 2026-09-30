import Foundation
import NiteSubmitCore

/// Real container headers, so the sniff has something true to read. The archive
/// tests write ASCII placeholders like "RIFF_WAV_HEADER_DATA_DUMMY", which do not
/// satisfy a RIFF/WAVE header and would pass on the extension fallback alone.
private func riffWAVEHeader() -> [UInt8] {
    var bytes: [UInt8] = Array("RIFF".utf8)
    bytes += [0x24, 0xF0, 0xFF, 0x7C]                       // chunk size, LE
    bytes += Array("WAVEfmt ".utf8)
    return bytes
}

private func mp3ID3Header() -> [UInt8] {
    Array("ID3".utf8) + [0x03, 0x00, 0x00, 0x00, 0x00, 0x0A, 0x7F]
}

private func ftypHeader(brand: String) -> [UInt8] {
    var bytes: [UInt8] = [0x00, 0x00, 0x00, 0x20]           // box size
    bytes += Array("ftyp".utf8)
    bytes += Array(brand.utf8)
    bytes += [0x00, 0x00, 0x02, 0x00]
    return bytes
}

func runMediaExtractorTests() {
    suite("MediaExtractor") {
        let fm = FileManager.default
        let tmp = fm.temporaryDirectory.appendingPathComponent("nite_media_\(UUID().uuidString)")
        try fm.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tmp) }

        func asset(_ name: String, _ bytes: [UInt8]) throws -> URL {
            let url = tmp.appendingPathComponent(name)
            try Data(bytes).write(to: url)
            return url
        }

        // The extension is the one piece of evidence a file browser got wrong when
        // someone renamed a file. A .wav holding MP3 audio used to be announced as
        // WAVE audio, and the app has no MP3 handling to back that up.
        scenario("a .wav that is really an MP3 is not labelled WAVE") {
            let renamed = try asset("renamed_take.wav", mp3ID3Header())
            check(FileKind.detect(url: renamed) != .audioWav,
                  "an MP3 wearing a .wav name is not reported as WAVE audio")
            eq(FileKind.detect(url: renamed), .unknown,
               "an MP3 with no kind of its own is reported as a plain asset")
            // A bare MPEG frame sync (no ID3 tag) is the same file with the tag
            // stripped, and must not slip through the extension either.
            let bare = try asset("renamed_take2.wav", [0xFF, 0xFB, 0x90, 0x00, 0x00, 0x00])
            check(FileKind.detect(url: bare) != .audioWav,
                  "a bare MPEG frame sync wearing a .wav name is not WAVE either")
        }

        scenario("real headers are recognised regardless of the extension") {
            let wav = try asset("stem.bin", riffWAVEHeader())
            eq(FileKind.detect(url: wav), .audioWav,
               "a RIFF/WAVE file is audio whatever it is called")
            let mov = try asset("clip.mp4", ftypHeader(brand: "qt  "))
            eq(FileKind.detect(url: mov), .videoMov,
               "a QuickTime ftyp brand is recognised even with a .mp4 name")
            let mp4 = try asset("clip2.mov", ftypHeader(brand: "isom"))
            eq(FileKind.detect(url: mp4), .videoMp4,
               "an ISO brand is MP4 even with a .mov name")
            let sevenZip = try asset("bundle.zip", [0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C])
            eq(FileKind.detect(url: sevenZip), .archive7z,
               "a 7z signature wins over a .zip name")
            let pdf = try asset("scan.png", Array("%PDF-1.7\n".utf8))
            eq(FileKind.detect(url: pdf), .pdf, "a %PDF header is recognised whatever the extension")
        }

        // A .docx and a .zip share a header, so the extension is the only thing
        // that can tell them apart and must not be overridden.
        scenario("a Word document keeps its kind, because it is a ZIP underneath") {
            let docx = try asset("essay.docx", [0x50, 0x4B, 0x03, 0x04, 0x14, 0x00])
            eq(FileKind.detect(url: docx), .docx, "a ZIP-headered .docx is still a Word document")
            let zip = try asset("bundle2.docx", [0x50, 0x4B, 0x03, 0x04, 0x14, 0x00])
            eq(FileKind.detect(url: zip), .docx,
               "a ZIP-headered .docx is left alone: the header cannot tell it from a Word file")
        }

        scenario("an empty or unrecognised file falls back to its extension") {
            let empty = try asset("recording.wav", [])
            eq(FileKind.detect(url: empty), .audioWav,
               "an empty .wav has no header to go on, so the name decides")
            let unknown = try asset("notes.txt", Array("just some text".utf8))
            eq(FileKind.detect(url: unknown), .unknown, "a text file stays unknown")
            let missing = tmp.appendingPathComponent("not_here.wav")
            eq(FileKind.detect(url: missing), .audioWav,
               "a file that is not there falls back to the extension rather than failing")
        }

        // A filename is the weakest evidence there is. These used to be MEDIUM, so
        // a camera's date stamp became a student number at a confidence the app
        // treats as good enough to build a submission name from.
        scenario("a camera date stamp in a filename is not a student number at medium confidence") {
            let metadata = MediaExtractor().extractMetadata(at: asset_stub("IMG_20240115.jpg"))
            eq(metadata.studentId.value ?? "", "20240115",
               "the filename match is still offered, so the student can correct it")
            eq(metadata.studentId.confidence, .low,
               "a student number guessed from a filename is LOW confidence")
        }

        scenario("a TAKE-prefixed filename is not a module code at medium confidence") {
            let metadata = MediaExtractor().extractMetadata(at: asset_stub("TAKE1234.mov"))
            eq(metadata.moduleCode.value ?? "", "TAKE1234",
               "the filename match is still offered, so the student can correct it")
            eq(metadata.moduleCode.confidence, .low,
               "a module code guessed from a filename is LOW confidence")
        }

        scenario("a real student number in a filename is still found, just not trusted") {
            let metadata = MediaExtractor().extractMetadata(at: asset_stub("1048291_Audio_Stem.wav"))
            eq(metadata.studentId.value ?? "", "1048291", "the number in the filename is still detected")
            check(metadata.studentId.confidence <= .low,
                  "a filename-only student number never rises above LOW confidence")
        }
    }
}

/// The filename-only detectors read the name, not the bytes, so these cases do
/// not need a real file on disk.
private func asset_stub(_ name: String) -> URL {
    URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(name)
}
