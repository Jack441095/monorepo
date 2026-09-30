import Foundation
import NiteSubmitCore
import CryptoKit

func sha256(_ url: URL) throws -> String {
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func runFileOperationTests() {
    suite("FileOperations") {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("nitesubmit-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let op = FileOperator()

        func makePDF(_ name: String, bytes: [UInt8] = [0x25, 0x50, 0x44, 0x46]) throws -> URL {
            let url = tmp.appendingPathComponent(name)
            try Data(bytes).write(to: url)
            return url
        }

        // Hard regression: CREATE RENAMED COPY must never alter original bytes.
        scenario("createRenamedCopy preserves the source") {
            let src = try makePDF("original.pdf", bytes: (0..<4096).map { UInt8($0 % 256) })
            let before = try sha256(src)
            _ = try op.createRenamedCopy(source: src, directory: tmp,
                                          newBaseName: "12345678_Project", policy: .error)
            eq(try sha256(src), before, "COPY preserves original bytes exactly")
            check(FileManager.default.fileExists(
                atPath: tmp.appendingPathComponent("12345678_Project.pdf").path), "copy exists")
        }

        // A symlinked source is refused rather than followed. Copying through the
        // link would pull bytes from outside the folder the user picked into a
        // submission under a name they never typed, and the hash check cannot
        // catch it because the link's target is a valid PDF.
        scenario("a symlinked source is refused, not followed") {
            let outside = FileManager.default.temporaryDirectory
                .appendingPathComponent("nitesubmit-tests-outside-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: outside) }
            let real = outside.appendingPathComponent("private_notes.pdf")
            try Data((0..<1024).map { UInt8($0 % 251) }).write(to: real)
            let alias = tmp.appendingPathComponent("link_into_private.pdf")
            try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: real)
            throwsError(try op.createRenamedCopy(source: alias, directory: tmp,
                                                 newBaseName: "stolen", policy: .error),
                        "symlinked source is refused")
            check(!FileManager.default.fileExists(atPath: tmp.appendingPathComponent("stolen.pdf").path),
                  "refused symlink leaves nothing at the destination")
            check(try Data(contentsOf: real).count == 1024,
                  "refused symlink leaves the outside file untouched")
            // Every other entry point shares the same gate.
            throwsError(try op.renameOriginal(source: alias, newBaseName: "moved", policy: .error),
                        "renaming a symlinked source is refused too")
        }

        // The staging file is a hidden sibling of the destination, so a copy that
        // fails partway must not leave a zero-byte or truncated file where the
        // submission should be. The old temporaryDirectory staging also made the
        // final move a cross-volume copy, which a full disk could truncate.
        scenario("a failed write leaves no partial file at the destination") {
            let roDir = tmp.appendingPathComponent("read-only-dest")
            try FileManager.default.createDirectory(at: roDir, withIntermediateDirectories: true)
            let src = try makePDF("blocked_source.pdf", bytes: (0..<4096).map { UInt8($0 % 256) })
            try FileManager.default.setAttributes([.posixPermissions: 0o555], ofItemAtPath: roDir.path)
            defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: roDir.path) }
            throwsError(try op.createRenamedCopy(source: src, directory: roDir,
                                                 newBaseName: "blocked", policy: .error),
                        "unwritable destination folder fails instead of writing a partial file")
            check(!FileManager.default.fileExists(atPath: roDir.appendingPathComponent("blocked.pdf").path),
                  "failed copy leaves no file at the destination")
            let leftovers = (try? FileManager.default.contentsOfDirectory(atPath: roDir.path)) ?? []
            check(leftovers.isEmpty,
                  "failed copy leaves no staging file behind (found \(leftovers.count) items)")
        }

        // Same story when the destination already holds a previous version: it keeps
        // its bytes rather than being deleted to make room for the new copy.
        scenario("a failed forced replace leaves the previous file intact") {
            let roDir = tmp.appendingPathComponent("read-only-existing")
            try FileManager.default.createDirectory(at: roDir, withIntermediateDirectories: true)
            let existing = roDir.appendingPathComponent("report.pdf")
            try Data("KEEP-ME".utf8).write(to: existing)
            let src = try makePDF("new_report.pdf", bytes: (0..<4096).map { UInt8($0 % 256) })
            try FileManager.default.setAttributes([.posixPermissions: 0o555], ofItemAtPath: roDir.path)
            defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: roDir.path) }
            throwsError(try op.createRenamedCopy(source: src, directory: roDir,
                                                 newBaseName: "report", policy: .replace),
                        "forced replace into an unwritable folder fails")
            eq(String(decoding: try Data(contentsOf: existing), as: UTF8.self), "KEEP-ME",
               "failed forced replace leaves the previous file intact")
        }

        // An occupied name range must be walked, never overwritten. The name is
        // re-claimed with an exclusive create at the moment of the write rather
        // than merely checked with fileExists() during the scan, so a name taken
        // between those two steps loses the race instead of the file.
        scenario("appendCounter walks a fully occupied name range") {
            let src = try makePDF("racer.pdf")
            for n in ["report.pdf", "report_1.pdf", "report_2.pdf"] {
                try Data("\(n)-ORIGINAL".utf8).write(to: tmp.appendingPathComponent(n))
            }
            let r = try op.createRenamedCopy(source: src, directory: tmp,
                                             newBaseName: "report", policy: .appendCounter)
            eq(r.newFilename ?? "", "report_3.pdf",
               "append counter skips a fully occupied name range")
            for n in ["report.pdf", "report_1.pdf", "report_2.pdf"] {
                eq(String(decoding: try Data(contentsOf: tmp.appendingPathComponent(n)), as: UTF8.self),
                   "\(n)-ORIGINAL", "\(n) keeps its bytes when the counter moves past it")
            }
        }

        // RENAME ORIGINAL: content hash identical, only path changes.
        scenario("renameOriginal keeps bytes and moves the path") {
            let src = try makePDF("bad_name.pdf", bytes: (0..<2048).map { UInt8(($0 * 7) % 256) })
            let hash = try sha256(src)
            _ = try op.renameOriginal(source: src, newBaseName: "good_name", policy: .error)
            eq(try sha256(tmp.appendingPathComponent("good_name.pdf")), hash,
               "RENAME preserves content hash")
            check(!FileManager.default.fileExists(atPath: src.path), "old path gone after rename")
        }

        scenario("undo restores the original filename") {
            let src = try makePDF("a.pdf")
            let receipt = try op.renameOriginal(source: src, newBaseName: "b", policy: .error)
            try op.undo(receipt)
            check(FileManager.default.fileExists(atPath: src.path), "undo restores original name")
        }

        // A collision-resolved original rename must still produce a usable
        // undo receipt and restore the original path.
        scenario("a counter-resolved rename is still undoable") {
            let src = try makePDF("numbered_source.pdf")
            _ = try makePDF("numbered_target.pdf")
            let receipt = try op.renameOriginal(source: src, newBaseName: "numbered_target",
                                                policy: .appendCounter)
            eq(receipt.newFilename ?? "", "numbered_target_1.pdf",
               "numbered original rename records final filename")
            try op.undo(receipt)
            check(FileManager.default.fileExists(atPath: src.path),
                  "numbered original rename remains undoable")
        }

        scenario("collision policies") {
            let src = try makePDF("s.pdf")
            _ = try makePDF("exists.pdf")
            throwsError(try op.createRenamedCopy(source: src, directory: tmp,
                                                 newBaseName: "exists", policy: .error),
                        "collision with .error policy refuses")
            _ = try makePDF("name.pdf")
            let r = try op.createRenamedCopy(source: src, directory: tmp,
                                              newBaseName: "name", policy: .appendCounter)
            eq(r.newFilename ?? "", "name_1.pdf", "append counter")
        }

        scenario("failures leave the source alone") {
            let ghost = tmp.appendingPathComponent("ghost.pdf")
            throwsError(try op.createRenamedCopy(source: ghost, directory: tmp,
                                                 newBaseName: "x", policy: .error),
                        "missing source fails safely")
            let src = try makePDF("unsafe_source.pdf")
            throwsError(try op.createRenamedCopy(source: src, directory: tmp,
                                                 newBaseName: "../escape", policy: .error),
                        "path-like destination name fails safely")
            let s2 = try makePDF("s2.pdf")
            throwsError(try op.resolveDestination(original: s2,
                                                  directory: tmp.appendingPathComponent("nope"),
                                                  newBaseName: "x", policy: .error),
                        "missing destination folder fails safely")
            let same = try makePDF("same_name.pdf")
            throwsError(try op.createRenamedCopy(source: same, directory: tmp,
                                                 newBaseName: "same_name", policy: .replace),
                        "same-path replacement fails before changing the source")
            check(FileManager.default.fileExists(atPath: same.path),
                  "same-path replacement leaves source intact")
        }

        scenario("unicode and long names round trip") {
            let src = try makePDF("s3.pdf")
            let name = "Zoë_Müller_" + String(repeating: "é", count: 100)
            let r = try op.createRenamedCopy(source: src, directory: tmp,
                                              newBaseName: name, policy: .error)
            eq(r.newFilename ?? "", name + ".pdf", "unicode long name round trip")
        }

        scenario("settings round trip") {
            let s = AppSettings(template: "{student_id}", presetId: "module_id",
                                renameMode: .renameOriginal, caseStyle: .snakeCase,
                                universityPresetId: "harvard",
                                documentIdentityPolicy: .nameRequired)
            s.save(to: tmp)
            let loaded = AppSettings.load(from: tmp)
            eq(loaded?.template ?? "", "{student_id}", "settings template persisted")
            check(loaded?.renameMode == .renameOriginal, "settings mode persisted")
            eq(loaded?.universityPresetId ?? "", "harvard", "university profile persisted")
            check(loaded?.documentIdentityPolicy == .nameRequired,
                  "document identity policy persisted")
            let directoryMode = (try? FileManager.default.attributesOfItem(atPath: tmp.path)[.posixPermissions] as? NSNumber)?.intValue
            let fileMode = (try? FileManager.default.attributesOfItem(atPath: tmp.appendingPathComponent("settings.json").path)[.posixPermissions] as? NSNumber)?.intValue
            eq(directoryMode ?? 0, 0o700, "settings directory is owner-only")
            eq(fileMode ?? 0, 0o600, "settings file is owner-only")
        }

        scenario("student-number onboarding state persists") {
            let s = AppSettings(defaultStudentId: "12345678",
                                hasPromptedForDefaultStudentId: true)
            s.save(to: tmp)
            let loaded = AppSettings.load(from: tmp)
            eq(loaded?.defaultStudentId ?? "", "12345678", "saved student number persisted")
            check(loaded?.hasPromptedForDefaultStudentId == true,
                  "student-number onboarding state persisted")
        }

        scenario("a custom template clears the built-in presets") {
            var edited = AppSettings(template: "{student_id}_{project_title}",
                                     presetId: "id_project",
                                     universityPresetId: "harvard")
            edited.applyCustomTemplate("{student_id}_{module_code}_{project_title}")
            edited.save(to: tmp)
            let loaded = AppSettings.load(from: tmp)
            eq(loaded?.template ?? "", "{student_id}_{module_code}_{project_title}",
               "custom template edit persisted")
            eq(loaded?.presetId ?? "", "custom",
               "custom template edit clears built-in preset")
            eq(loaded?.universityPresetId ?? "", "custom",
               "custom template edit clears university profile")
        }

        scenario("a legacy settings file still decodes") {
            // Older settings files have no onboarding key and should still
            // decode safely, allowing the new first-run prompt once.
            let legacy = #"{"template":"{student_id}_{project_title}"}"#.data(using: .utf8)!
            try legacy.write(to: tmp.appendingPathComponent("settings.json"))
            let loaded = AppSettings.load(from: tmp)
            check(loaded?.hasPromptedForDefaultStudentId == false,
                  "legacy settings default to an unshown onboarding prompt")
            check(loaded?.documentIdentityPolicy == .noRule,
                  "legacy settings default to no document identity rule")
            let repairedMode = (try? FileManager.default.attributesOfItem(atPath: tmp.appendingPathComponent("settings.json").path)[.posixPermissions] as? NSNumber)?.intValue
            eq(repairedMode ?? 0, 0o600, "legacy settings permissions repaired on load")
        }

        scenario("preset catalog and safe defaults") {
            // A new install must use the safe ID + Project rule. Module code is
            // optional unless the user explicitly chooses a module-bearing rule.
            let freshDefaults = AppSettings()
            eq(freshDefaults.template, "{student_id}_{project_title}",
               "fresh settings use the safe ID + Project template")
            eq(freshDefaults.presetId, "id_project",
               "fresh settings select the ID + Project preset")
            eq(Presets.universityProfiles.first(where: { $0.id == "custom" })?.template ?? "",
               "{student_id}_{project_title}",
               "Generic university profile matches the safe default")

            // The two researched profiles are selectable and remain editable
            // generic patterns rather than claims of a universal institutional rule.
            let profiles = Presets.universityProfiles
            check(profiles.contains(where: { $0.id == "harvard" }), "Harvard profile available")
            check(profiles.contains(where: { $0.id == "uk_coursework" }), "UK coursework profile available")
            check(profiles.contains(where: { $0.id == "uk_assignment_code" }),
                  "UK assignment-code profile available")
            check(profiles.contains(where: { $0.id == "us_coursework" }), "US coursework profile available")
            check(profiles.contains(where: { $0.id == "us_assignment_code" }),
                  "US assignment-code profile available")
            check(profiles.contains(where: { $0.id == "chicago" }), "Chicago profile available")
            eq(profiles.first(where: { $0.id == "custom" })?.template ?? "",
               "{student_id}_{project_title}", "Generic profile template")
            check(profiles.contains(where: { $0.id == "anonymous_candidate" }),
                  "anonymous candidate profile available")
            check(Presets.builtIn.contains(where: { $0.id == "assignment_candidate_project" }),
                  "assignment/candidate profile available")
            check(Presets.builtIn.contains(where: { $0.id == "group_project" }),
                  "group ID profile available")
            check(Presets.builtIn.contains(where: { $0.id == "id_name_project" }),
                  "student-name filename profile available")
            eq(profiles.first(where: { $0.id == "harvard" })?.template ?? "",
               "{student_id}_{project_title}", "Harvard profile template")
            eq(profiles.first(where: { $0.id == "uk_coursework" })?.template ?? "",
               "{module_code}_{student_id}_{project_title}", "UK coursework profile template")
            eq(profiles.first(where: { $0.id == "uk_assignment_code" })?.template ?? "",
               "{assignment_code}_{student_id}_{project_title}",
               "UK assignment-code profile template")
            eq(profiles.first(where: { $0.id == "us_coursework" })?.template ?? "",
               "{last_name}_{first_name}_{project_title}", "US coursework profile template")
            eq(profiles.first(where: { $0.id == "us_assignment_code" })?.template ?? "",
               "{last_name}_{assignment_code}", "US assignment-code profile template")
            eq(profiles.first(where: { $0.id == "chicago" })?.template ?? "",
               "{first_name}_{last_name}_{project_title}", "Chicago profile template")
            eq(profiles.first(where: { $0.id == "id_name_project" })?.template ?? "",
               "{student_id}_{full_name}_{project_title}",
               "ID plus student-name profile template")
            eq(profiles.first(where: { $0.id == "anonymous_candidate" })?.template ?? "",
               "{candidate_number}_{project_title}", "anonymous candidate profile template")
            eq(Presets.builtIn.first(where: { $0.id == "group_project" })?.template ?? "",
               "{group_id}_{project_title}", "group ID profile template")
            check(!(profiles.first(where: { $0.id == "anonymous_candidate" })?.template.variables() ?? [])
                .contains(where: { ["first_name", "last_name", "full_name"].contains($0) }),
                  "anonymous candidate profile excludes name fields")
            check(TemplateEngine.render(template: "{assignment_code}_{candidate_number}_{project_title}",
                                        values: ["assignment_code": "MEX4E001R~001",
                                                 "candidate_number": "004812",
                                                 "project_title": "Essay"],
                                        originalName: "x")
                  == "MEX4E001R~001_004812_Essay",
                  "assignment identifiers remain deterministic")

            let missingTemplate = #"{"defaultStudentId":"12345678"}"#.data(using: .utf8)!
            let decodedFresh = try JSONDecoder().decode(AppSettings.self, from: missingTemplate)
            eq(decodedFresh.template, "{student_id}_{project_title}",
               "settings without a template migrate to the safe default")
            eq(decodedFresh.presetId, "id_project",
               "settings without a preset migrate to ID + Project")
        }

        scenario("zero-byte file copy stays consistent") {
            let src = try makePDF("zero.pdf", bytes: [])
            let h1 = try sha256(src)
            let r = try op.createRenamedCopy(source: src, directory: tmp,
                                              newBaseName: "z", policy: .appendCounter)
            let written = r.newFilename ?? ""
            check(!written.isEmpty, "zero-byte copy reports the filename it wrote")
            eq(try sha256(tmp.appendingPathComponent(written)), h1, "zero-byte copy consistent")
        }
    }
}
