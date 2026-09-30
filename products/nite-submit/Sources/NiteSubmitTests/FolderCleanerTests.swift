import Foundation
import NiteSubmitCore

func runFolderCleanerTests() {
    suite("Library Folder Cleaner (FolderScanner & OrganizationRulesEngine)") {
        let fm = FileManager.default
        // 1. FileCategory classification test
        check(FileCategory.categorize(extension: "pdf") == .documents, "PDF -> Documents")
        check(FileCategory.categorize(extension: "wav") == .audio, "WAV -> Audio")
        check(FileCategory.categorize(extension: "mp4") == .video, "MP4 -> Video")
        check(FileCategory.categorize(extension: "png") == .images, "PNG -> Images")
        check(FileCategory.categorize(extension: "7z") == .archives, "7z -> Archives")
        check(FileCategory.categorize(extension: "swift") == .code, "Swift -> Code")
        check(FileCategory.categorize(extension: "xyz") == .other, "XYZ -> Other")

        // 2. Recursive folder scanner test
        let tempDir = fm.temporaryDirectory.appendingPathComponent("nite_cleaner_test_\(UUID().uuidString)")
        try fm.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: tempDir) }

        let file1 = tempDir.appendingPathComponent("essay.pdf")
        let file2 = tempDir.appendingPathComponent("track.wav")
        let file3 = tempDir.appendingPathComponent("video.mp4")
        let subDir = tempDir.appendingPathComponent("SubFolder")
        try fm.createDirectory(at: subDir, withIntermediateDirectories: true)
        let file4 = subDir.appendingPathComponent("code.swift")

        fm.createFile(atPath: file1.path, contents: Data("PDF Data".utf8))
        fm.createFile(atPath: file2.path, contents: Data("WAV Data".utf8))
        fm.createFile(atPath: file3.path, contents: Data("MP4 Data".utf8))
        fm.createFile(atPath: file4.path, contents: Data("Swift Data".utf8))

        let scanner = FolderScanner()
        // 3. OrganizationRulesEngine test - Group By Category
        scenario("scanner and category plan") {
            let manifest = try scanner.scan(directoryURL: tempDir)
            check(manifest.totalFiles == 4, "FolderScanner found 4 files in recursive traversal")
            check(manifest.files.contains(where: { $0.category == .documents }), "Manifest contains Documents category")
            check(manifest.files.contains(where: { $0.category == .audio }), "Manifest contains Audio category")
            check(manifest.files.contains(where: { $0.category == .video }), "Manifest contains Video category")
            check(manifest.files.contains(where: { $0.category == .code }), "Manifest contains Code category")

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

        // 5. A colliding plan must refuse without force and leave the existing
        // file untouched. This guards the September fix where the executor
        // hardcoded .replace and silently overwrote library files.
        scenario("colliding plan refuses without force") {
            let collideDir = fm.temporaryDirectory.appendingPathComponent("nite_collide_test_\(UUID().uuidString)")
            try fm.createDirectory(at: collideDir, withIntermediateDirectories: true)
            defer { try? fm.removeItem(at: collideDir) }
            let src = collideDir.appendingPathComponent("incoming.pdf")
            let destDir = collideDir.appendingPathComponent("Sorted")
            try fm.createDirectory(at: destDir, withIntermediateDirectories: true)
            let dest = destDir.appendingPathComponent("incoming.pdf")
            fm.createFile(atPath: src.path, contents: Data("NEW BYTES".utf8))
            fm.createFile(atPath: dest.path, contents: Data("KEEP ME".utf8))
            let collidingPlan = OrganizationPlan(
                targetDirectory: destDir,
                ruleType: .groupByCategory,
                actions: [ProposedFileAction(sourceURL: src, destinationURL: dest,
                                             actionType: .copy, reason: "test collision",
                                             hasCollision: true)])
            let op = FileOperator()
            let blocked = op.executeOrganizationPlan(collidingPlan)
            check(blocked.failedCount == 1, "Colliding plan fails the action without force")
            check(blocked.succeededCount == 0, "Colliding plan succeeds at nothing without force")
            check((try? Data(contentsOf: dest)) == Data("KEEP ME".utf8), "Colliding plan leaves the existing file untouched")
            check(blocked.actionReceipts.first?.success == false, "Colliding receipt records the refusal")
            let forced = op.executeOrganizationPlan(collidingPlan, forceOverwrite: true)
            check(forced.succeededCount == 1, "Colliding plan succeeds with explicit force")
            check((try? Data(contentsOf: dest)) == Data("NEW BYTES".utf8), "Forced plan replaces the destination")
            check(forced.actionReceipts.first?.message.contains("force") == true, "Forced receipt names the overwrite")
        }

        // 6. Two files whose names differ only in case are one file on a default
        // APFS volume, so the second must be flagged. The engine used to compare
        // the path exactly as written, saw no collision, and the executor then
        // wrote one submission over the other.
        scenario("a case-only filename clash is reported as a collision") {
            let clashDir = fm.temporaryDirectory.appendingPathComponent("nite_case_clash_\(UUID().uuidString)")
            let left = clashDir.appendingPathComponent("inbox-1", isDirectory: true)
            let right = clashDir.appendingPathComponent("inbox-2", isDirectory: true)
            try fm.createDirectory(at: left, withIntermediateDirectories: true)
            try fm.createDirectory(at: right, withIntermediateDirectories: true)
            defer { try? fm.removeItem(at: clashDir) }
            // Kept in separate source folders so a case-insensitive volume can
            // hold both: this is the "two module hand-ins" case.
            try Data("FIRST-SUBMISSION".utf8).write(to: left.appendingPathComponent("Report.pdf"))
            try Data("SECOND-SUBMISSION".utf8).write(to: right.appendingPathComponent("report.pdf"))

            let engine = OrganizationRulesEngine()
            let manifest = try FolderScanner().scan(directoryURL: clashDir)
            eq(manifest.totalFiles, 2, "both case variants are scanned as separate source files")
            let plan = engine.generatePlan(manifest: manifest, ruleType: .groupByCategory,
                                           destinationDirectory: clashDir.appendingPathComponent("sorted"),
                                           copyMode: true)
            eq(plan.collisionsCount, 1, "the second Report.pdf is flagged against the first")
            let clash = plan.actions.last { $0.hasCollision }
            check(clash?.sourceURL.lastPathComponent == "report.pdf",
                  "the later of the two case variants is the one flagged")
            // The comparison key is lowercased, but the plan still writes the name
            // exactly as the rule rendered it.
            check(clash?.destinationURL.lastPathComponent == "report.pdf",
                  "the flagged action still keeps its filename spelling")
        }

        // 7. A folder we cannot read must say so. Returning an empty manifest
        // made "permission denied" indistinguishable from "nothing to file", and
        // the cleaner then reported a tidy empty plan for a library it never saw.
        scenario("an unreadable folder is reported, not silently empty") {
            let locked = fm.temporaryDirectory.appendingPathComponent("nite_locked_\(UUID().uuidString)")
            try fm.createDirectory(at: locked, withIntermediateDirectories: true)
            defer {
                try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: locked.path)
                try? fm.removeItem(at: locked)
            }
            try Data("PRIVATE".utf8).write(to: locked.appendingPathComponent("secret.pdf"))
            try fm.setAttributes([.posixPermissions: 0o000], ofItemAtPath: locked.path)
            throwsError(try FolderScanner().scan(directoryURL: locked),
                        "a folder with no read permission throws instead of scanning as empty")
        }

        scenario("a folder that is not there throws too") {
            throwsError(try FolderScanner().scan(
                directoryURL: fm.temporaryDirectory.appendingPathComponent("nite_gone_\(UUID().uuidString)")),
                        "a missing folder throws instead of scanning as empty")
        }

        // 8. Enumeration order is filesystem order, so the same tree used to plan
        // a different sequence of suffixed names on every run.
        scenario("scan output is sorted by relative path, not by creation order") {
            let mixed = fm.temporaryDirectory.appendingPathComponent("nite_mixed_\(UUID().uuidString)")
            let nested = mixed.appendingPathComponent("2026", isDirectory: true)
            try fm.createDirectory(at: nested, withIntermediateDirectories: true)
            defer { try? fm.removeItem(at: mixed) }
            // Written in an order that matches neither the alphabet nor the
            // directory's own enumeration order.
            for name in ["zeta.pdf", "Alpha.pdf", "mid.pdf", "2026/inner.pdf", "beta.pdf"] {
                try Data("X".utf8).write(to: mixed.appendingPathComponent(name))
            }
            let manifest = try FolderScanner().scan(directoryURL: mixed)
            let paths = manifest.files.map(\.relativePath)
            eq(paths, ["2026/inner.pdf", "Alpha.pdf", "beta.pdf", "mid.pdf", "zeta.pdf"],
               "manifest paths come back in sorted order regardless of creation order")
            // The plan inherits that order, so the numbering of suffixed names is
            // reproducible run to run.
            let plan = OrganizationRulesEngine().generatePlan(
                manifest: manifest, ruleType: .groupByCategory,
                destinationDirectory: mixed.appendingPathComponent("sorted"))
            eq(plan.actions.map { $0.sourceURL.lastPathComponent },
               ["inner.pdf", "Alpha.pdf", "beta.pdf", "mid.pdf", "zeta.pdf"],
               "the organization plan follows the sorted scan order")
        }
    }
}
