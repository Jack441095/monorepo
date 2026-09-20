import Foundation
import NiteSubmitCore

func runFolderCleanerTests() {
    print("— Library Folder Cleaner (FolderScanner & OrganizationRulesEngine)")

    // 1. FileCategory classification test
    check(FileCategory.categorize(extension: "pdf") == .documents, "PDF -> Documents")
    check(FileCategory.categorize(extension: "wav") == .audio, "WAV -> Audio")
    check(FileCategory.categorize(extension: "mp4") == .video, "MP4 -> Video")
    check(FileCategory.categorize(extension: "png") == .images, "PNG -> Images")
    check(FileCategory.categorize(extension: "7z") == .archives, "7z -> Archives")
    check(FileCategory.categorize(extension: "swift") == .code, "Swift -> Code")
    check(FileCategory.categorize(extension: "xyz") == .other, "XYZ -> Other")

    // 2. Recursive folder scanner test
    let fm = FileManager.default
    let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_cleaner_test_\(UUID().uuidString)")
    try? fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? fm.removeItem(at: tempDir) }

    let file1 = tempDir.appendingPathComponent("essay.pdf")
    let file2 = tempDir.appendingPathComponent("track.wav")
    let file3 = tempDir.appendingPathComponent("video.mp4")
    let subDir = tempDir.appendingPathComponent("SubFolder")
    try? fm.createDirectory(at: subDir, withIntermediateDirectories: true)
    let file4 = subDir.appendingPathComponent("code.swift")

    fm.createFile(atPath: file1.path, contents: Data("PDF Data".utf8))
    fm.createFile(atPath: file2.path, contents: Data("WAV Data".utf8))
    fm.createFile(atPath: file3.path, contents: Data("MP4 Data".utf8))
    fm.createFile(atPath: file4.path, contents: Data("Swift Data".utf8))

    let scanner = FolderScanner()
    guard let manifest = try? scanner.scan(directoryURL: tempDir) else {
        check(false, "FolderScanner scan failed")
        return
    }

    check(manifest.totalFiles == 4, "FolderScanner found 4 files in recursive traversal")
    check(manifest.files.contains(where: { $0.category == .documents }), "Manifest contains Documents category")
    check(manifest.files.contains(where: { $0.category == .audio }), "Manifest contains Audio category")
    check(manifest.files.contains(where: { $0.category == .video }), "Manifest contains Video category")
    check(manifest.files.contains(where: { $0.category == .code }), "Manifest contains Code category")

    // 3. OrganizationRulesEngine test - Group By Category
    let engine = OrganizationRulesEngine()
    let plan = engine.generatePlan(manifest: manifest, ruleType: .groupByCategory, copyMode: true)
    check(plan.actions.count == 4, "Plan has 4 actions")
    check(plan.collisionsCount == 0, "Plan has 0 collisions")

    let pdfAction = plan.actions.first(where: { $0.sourceURL.lastPathComponent == "essay.pdf" })
    check(pdfAction?.destinationURL.path.contains("Documents/essay.pdf") == true, "essay.pdf target is Documents/essay.pdf")

    let wavAction = plan.actions.first(where: { $0.sourceURL.lastPathComponent == "track.wav" })
    check(wavAction?.destinationURL.path.contains("Audio/track.wav") == true, "track.wav target is Audio/track.wav")

    // 4. Execution & Dry Run Test
    let op = FileOperator()
    let dryReceipt = op.executeOrganizationPlan(plan, dryRun: true)
    check(dryReceipt.succeededCount == 4, "Dry-run succeeded for 4 actions")
    check(fm.fileExists(atPath: tempDir.appendingPathComponent("Documents/essay.pdf").path) == false, "Dry-run did not mutate disk")

    let realReceipt = op.executeOrganizationPlan(plan, dryRun: false)
    check(realReceipt.succeededCount == 4, "Real plan execution succeeded for 4 actions")
    check(fm.fileExists(atPath: tempDir.appendingPathComponent("Documents/essay.pdf").path) == true, "essay.pdf copied into Documents/")
    check(fm.fileExists(atPath: tempDir.appendingPathComponent("Audio/track.wav").path) == true, "track.wav copied into Audio/")
    check(fm.fileExists(atPath: tempDir.appendingPathComponent("Video/video.mp4").path) == true, "video.mp4 copied into Video/")
    check(fm.fileExists(atPath: tempDir.appendingPathComponent("Code/code.swift").path) == true, "code.swift copied into Code/")
}
