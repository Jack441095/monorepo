import Foundation
import NiteSubmitCore

func runBatchSafetyTests() {
    print("— Batch safety (confidence gate & path containment)")

    suite("SubmissionMetadata.lowConfidenceVariables") {
        // A rule built on {module_code} and {university} used to be waved through on values
        // the detector had only guessed at, so the batch wrote them without review.
        let guessed = SubmissionMetadata(
            studentName: Detection(value: "Jack Gandy", confidence: .high),
            studentId: Detection(value: "12345678", confidence: .high),
            university: Detection(value: "University of Example", confidence: .medium),
            moduleCode: Detection(value: "UFMXYZ-30-3", confidence: .medium),
            moduleTitle: Detection(value: "Interactive Audio Systems", confidence: .low))
        eq(guessed.lowConfidenceVariables(in: ["module_code", "module_title", "university"]),
           ["module_code", "module_title", "university"],
           "module code, module title and university are held at medium or low confidence")
        check(guessed.lowConfidenceVariables(in: ["student_id"]).isEmpty,
              "a rule that only prints the verified student number is not held")
        check(SubmissionMetadata().lowConfidenceVariables(in: ["project_title"]) == ["project_title"],
              "a missing detection is below HIGH, and only the variables the rule names are looked at")

        let allHigh = SubmissionMetadata(
            studentName: Detection(value: "Jack Gandy", confidence: .high),
            studentId: Detection(value: "12345678", confidence: .high),
            candidateNumber: Detection(value: "778812", confidence: .high),
            assignmentCode: Detection(value: "AE401", confidence: .high),
            groupId: Detection(value: "G4", confidence: .high),
            university: Detection(value: "University of Example", confidence: .high),
            moduleCode: Detection(value: "UFMXYZ-30-3", confidence: .high),
            moduleTitle: Detection(value: "Interactive Audio Systems", confidence: .high),
            projectTitle: Detection(value: "Room Acoustics Study", confidence: .high))
        check(allHigh.lowConfidenceVariables(in: ["first_name", "last_name", "full_name",
                                                   "student_id", "candidate_number",
                                                   "assignment_code", "group_id", "university",
                                                   "module_code", "module_title", "project_title",
                                                   "assignment_title"]).isEmpty,
              "every templated variable is released once all detections are HIGH")

        let onlyModuleHeld = SubmissionMetadata(
            studentName: Detection(value: "Jack Gandy", confidence: .high),
            studentId: Detection(value: "12345678", confidence: .high),
            university: Detection(value: "University of Example", confidence: .high),
            moduleCode: Detection(value: "UFMXYZ-30-3", confidence: .medium),
            moduleTitle: Detection(value: "Interactive Audio Systems", confidence: .high),
            projectTitle: Detection(value: "Room Acoustics Study", confidence: .high))
        eq(onlyModuleHeld.lowConfidenceVariables(in: ["module_code", "module_title", "university"]),
           ["module_code"],
           "one doubted variable holds a rule even when its neighbours verified clean")

        let weakName = SubmissionMetadata(
            studentName: Detection(value: "J G", confidence: .low))
        eq(weakName.lowConfidenceVariables(in: ["last_name"]), ["last_name"],
           "one name detection at LOW confidence holds a rule that prints the surname")

        let untitled = SubmissionMetadata()
        eq(untitled.lowConfidenceVariables(in: ["assignment_title"]), ["assignment_title"],
           "assignment_title is judged by the project title detection, missing included")
        eq(untitled.lowConfidenceVariables(in: ["student_id"]), ["student_id"],
           "a missing detection is below HIGH too — the batch's required-field gap names it separately")
    }

    suite("pathIsInside") {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("nite_batch_paths_\(UUID().uuidString)")
        let input = root.appendingPathComponent("in", isDirectory: true)
        let nested = input.appendingPathComponent("week 1", isDirectory: true)
        let out = root.appendingPathComponent("out", isDirectory: true)
        try? fm.createDirectory(at: nested, withIntermediateDirectories: true)
        try? fm.createDirectory(at: out, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }

        check(pathIsInside(input, input), "a directory is inside itself")
        check(pathIsInside(nested, input), "a child directory is inside its parent")
        check(!pathIsInside(out, input), "a sibling is not inside its sibling")
        check(!pathIsInside(input, nested), "a parent is not inside its child")
        check(!pathIsInside(out, out.appendingPathComponent("outgoing", isDirectory: true)),
              "a sibling that only shares a name prefix is not inside")
        check(pathIsInside(input.appendingPathComponent("nested/deep.pdf"), input),
              "a nested file is inside the input tree")
        check(pathIsInside(root.appendingPathComponent("in/../in", isDirectory: true), input),
              "a dot-dot path is canonicalized before the comparison")

        // The escape users actually hit: an --out typed outside the input tree that a symlink
        // drops back inside, so the next run scans its own output.
        let elsewhere = root.appendingPathComponent("elsewhere", isDirectory: true)
        try? fm.createDirectory(at: elsewhere, withIntermediateDirectories: true)
        let backDoor = elsewhere.appendingPathComponent("into-input", isDirectory: true)
        try? fm.createSymbolicLink(at: backDoor, withDestinationURL: input)
        check(pathIsInside(backDoor, input),
              "a symlinked output that resolves into the input tree counts as inside it")
        check(pathIsInside(backDoor.appendingPathComponent("renamed copy.pdf"), input),
              "a file that does not exist yet still resolves through the symlinked parent")
        check(!pathIsInside(out, backDoor), "a real sibling is not inside a symlink's target")
    }
}
