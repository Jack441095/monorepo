import Foundation
import NiteSubmitCore

let templateValues = [
    "student_id": "12345678",
    "module_code": "UFMXYZ-30-3",
    "project_title": "Interactive Audio Systems",
    "full_name": "Jack Gandy",
    "first_name": "Jack",
    "last_name": "Gandy",
    "group_id": "G-17",
]

func runTemplateTests() {
    suite("TemplateEngine") {
        var v = templateValues
        let out = TemplateEngine.render(
            template: "{student_id}_{module_code}_{last_name}_{project_title}",
            values: v, originalName: "final_FINAL_v7", date: Date(timeIntervalSince1970: 0))
        eq(out!, "12345678_UFMXYZ-30-3_Gandy_Interactive_Audio_Systems", "basic render")

        let harvard = Presets.universityProfiles.first(where: { $0.id == "harvard" })!
        let ukCoursework = Presets.universityProfiles.first(where: { $0.id == "uk_coursework" })!
        let usCoursework = Presets.universityProfiles.first(where: { $0.id == "us_coursework" })!
        let usAssignmentCode = Presets.universityProfiles.first(where: { $0.id == "us_assignment_code" })!
        let chicago = Presets.universityProfiles.first(where: { $0.id == "chicago" })!
        let idAndName = Presets.universityProfiles.first(where: { $0.id == "id_name_project" })!
        eq(TemplateEngine.render(template: harvard.template, values: templateValues,
                                 originalName: "x")!,
           "12345678_Interactive_Audio_Systems",
           "Harvard generic profile renders ID and project")
        eq(TemplateEngine.render(template: ukCoursework.template, values: templateValues,
                                 originalName: "x")!,
           "UFMXYZ-30-3_12345678_Interactive_Audio_Systems",
           "UK coursework profile renders module, ID, and project")
        eq(TemplateEngine.render(template: usCoursework.template, values: templateValues,
                                 originalName: "x")!,
           "Gandy_Jack_Interactive_Audio_Systems",
           "US coursework profile renders surname, first name, and project")
        var assignmentValues = templateValues
        assignmentValues["assignment_code"] = "A3"
        eq(TemplateEngine.render(template: usAssignmentCode.template, values: assignmentValues,
                                 originalName: "x")!,
           "Gandy_A3",
           "US assignment-code profile renders surname and assignment code")
        let groupTemplate = Presets.builtIn.first(where: { $0.id == "group_project" })!
        eq(TemplateEngine.render(template: groupTemplate.template, values: templateValues,
                                 originalName: "x")!,
           "G-17_Interactive_Audio_Systems",
           "group profile renders explicit group ID and project")
        eq(TemplateEngine.render(template: chicago.template, values: templateValues,
                                 originalName: "x")!,
           "Jack_Gandy_Interactive_Audio_Systems",
           "Chicago generic profile renders first/last name and project")
        eq(TemplateEngine.render(template: idAndName.template, values: templateValues,
                                 originalName: "x")!,
           "12345678_Jack_Gandy_Interactive_Audio_Systems",
           "ID plus student-name profile renders all identity fields")
        let fullNameWithMiddle = SubmissionMetadata(
            studentName: Detection(value: "Juan Pablo Gomez", confidence: .high),
            studentId: Detection(value: "75589", confidence: .high),
            projectTitle: Detection(value: "The Invisible Carnival", confidence: .high))
        eq(TemplateEngine.render(template: idAndName.template,
                                 values: fullNameWithMiddle.variableMap(),
                                 originalName: "x")!,
           "75589_Juan_Pablo_Gomez_The_Invisible_Carnival",
           "ID plus student-name profile preserves middle names")
        let commaOrderedMetadata = SubmissionMetadata(
            studentName: Detection(value: "Gomez, Juan Pablo", confidence: .high),
            projectTitle: Detection(value: "A Title", confidence: .high))
        eq(TemplateEngine.render(template: chicago.template,
                                 values: commaOrderedMetadata.variableMap(),
                                 originalName: "x")!,
           "Juan_Gomez_A_Title",
           "Chicago profile normalises comma-ordered names")

        v["student_id"] = nil
        check(TemplateEngine.render(template: "{student_id}_{project_title}",
                                    values: v, originalName: "x") == nil,
              "missing student_id blocks render")
        let missingManualName = SubmissionMetadata(
            studentId: Detection(value: "75589", confidence: .high),
            projectTitle: Detection(value: "A Title", confidence: .medium))
        check(TemplateEngine.missingRequiredFields(idAndName.template,
                                                   values: missingManualName.variableMap())
                .contains(where: { $0.contains("Student name") }),
              "missing student name blocks a name-bearing rule")
        let completedManualName = SubmissionMetadata(
            studentName: Detection(value: "Alex Student", confidence: .high, rule: "manual"),
            studentId: Detection(value: "75589", confidence: .high),
            projectTitle: Detection(value: "A Title", confidence: .medium))
        check(TemplateEngine.missingRequiredFields(idAndName.template,
                                                   values: completedManualName.variableMap()).isEmpty,
              "manual student name clears the name-bearing required-field gate")
        check(TemplateEngine.render(template: "{project_title}",
                                    values: ["student_id": "1"], originalName: "x") == nil,
              "missing project title blocks render")
        check(TemplateEngine.render(template: "{first_name}_{last_name}_{project_title}",
                                    values: ["project_title": "A Title"], originalName: "x") == nil,
              "missing first/last name blocks Chicago-style render")
        check(TemplateEngine.render(template: "{candidate_number}_{project_title}",
                                    values: ["project_title": "A Title"], originalName: "x") == nil,
              "missing candidate number blocks anonymous render")
        check(TemplateEngine.render(template: "{group_id}_{project_title}",
                                    values: ["project_title": "A Title"], originalName: "x") == nil,
              "missing group ID blocks group render")
        let anonymous = TemplateEngine.render(
            template: "{candidate_number}_{project_title}",
            values: ["candidate_number": "004812", "project_title": "A Title"],
            originalName: "x")
        eq(anonymous!, "004812_A_Title", "anonymous candidate profile preserves leading zeroes")
        v["student_id"] = templateValues["student_id"]!

        check(TemplateEngine.render(template: "{student_id}_{module_title}_{project_title}",
                                    values: v, originalName: "x") == nil,
              "missing module title blocks a module-title naming rule")
        check(TemplateEngine.render(template: "{student_id}_{university}_{project_title}",
                                    values: v, originalName: "x") == nil,
              "missing university blocks a university naming rule")
        check(TemplateEngine.render(template: "{student_id}_{module_code}_{project_title}",
                                    values: ["student_id": "1", "project_title": "A Title"],
                                    originalName: "x") == nil,
              "missing module code blocks a module-code naming rule")
        check(TemplateEngine.render(template: "{student_id}_{assignment_title}",
                                    values: ["student_id": "1"], originalName: "x") == nil,
              "missing assignment title blocks an assignment-title naming rule")

        check(!TemplateEngine.validate("{bogus_field}").isEmpty, "unknown variable flagged")
        check(TemplateEngine.validate("{student_id}_{date}").isEmpty, "known variables accepted")
        check(!TemplateEngine.validate("{student_id").isEmpty,
              "unmatched opening brace is rejected")
        check(!TemplateEngine.validate("{student id}_{project_title}").isEmpty,
              "placeholder with spaces is rejected")
        check(TemplateEngine.render(template: "{student_id}_{project_title",
                                    values: templateValues, originalName: "x") == nil,
              "malformed template cannot render")
        check(TemplateEngine.validate("{candidate_number}_{project_title}").isEmpty,
              "candidate number variable accepted")
        check(TemplateEngine.validate("{assignment_code}_{project_title}").isEmpty,
              "assignment code variable accepted")

        let dated = TemplateEngine.render(template: "{student_id}_{date}", values: v,
                                          originalName: "x", date: Date(timeIntervalSince1970: 0))
        eq(dated!, "12345678_1970-01-01", "date variable")

        let orig = TemplateEngine.render(template: "{original_name}_renamed", values: v,
                                         originalName: "report draft")
        eq(orig!, "report_draft_renamed", "original name variable")

        let collapsed = TemplateEngine.render(template: "{student_id}__{university}__{project_title}",
                                              values: v.merging(["university": "Berklee College"]) { current, _ in current },
                                              originalName: "x")
        check(collapsed!.contains("__") == false, "no double underscores")

        var dirty = v
        dirty["project_title"] = "Audio: Final/Mix?"
        let sanitised = TemplateEngine.render(template: "{student_id}_{project_title}",
                                              values: dirty, originalName: "x")
        eq(sanitised!, "12345678_Audio_Final_Mix", "sanitisation applied in templates")

        let ambiguousMetadata = SubmissionMetadata(
            studentName: Detection(value: "Majid Abdul", confidence: .medium,
                                   rule: "title_page_student_name",
                                   candidates: ["Islam MD.Ashikul"]),
            projectTitle: Detection(value: "A Group Project", confidence: .high,
                                    rule: "label_project_title"))
        eq(TemplateEngine.ambiguousRequiredFields(
            "{first_name}_{last_name}_{project_title}", metadata: ambiguousMetadata).first ?? "",
           "Student name", "name-bearing group filename requires an explicit choice")
        check(TemplateEngine.ambiguousRequiredFields(
            "{student_id}_{project_title}", metadata: ambiguousMetadata).isEmpty,
              "ID-only filename does not require a group-name choice")

        let manualMetadata = SubmissionMetadata(
            studentName: Detection(value: "Majid Abdul", confidence: .high,
                                   rule: "manual", candidates: []),
            projectTitle: ambiguousMetadata.projectTitle)
        check(TemplateEngine.ambiguousRequiredFields(
            "{first_name}_{last_name}_{project_title}", metadata: manualMetadata).isEmpty,
              "manual group-name choice clears the ambiguity gate")
        let selectedAlternativeMetadata = SubmissionMetadata(
            studentName: Detection(value: "Islam MD.Ashikul", confidence: .high,
                                   rule: "manual", candidates: []),
            projectTitle: ambiguousMetadata.projectTitle)
        check(TemplateEngine.ambiguousRequiredFields(
            "{first_name}_{last_name}_{project_title}", metadata: selectedAlternativeMetadata).isEmpty,
              "selected candidate is treated as an explicit manual choice")
    }

    suite("Localization") {
        eq(NiteLocalization().label(.studentName),
           "Student name", "student field is explicit in the UI vocabulary")
        eq(NiteLocalization(language: .spanish).label(.studentID),
           "Student number", "untranslated languages use reviewed English fallback")
        check(NiteLocalization(language: .spanish).isEnglishFallback,
              "fallback is visible to the UI layer")
        eq(MetadataField.assignmentCode.localizationKey.rawValue,
           "assignment_code", "assignment code has a stable localization key")
        eq(MetadataField.groupId.localizationKey.rawValue,
           "group_id", "group ID has a stable localization key")
        eq(MetadataField.projectTitle.localizationKey.rawValue,
           "project_title", "project title has a stable localization key")
    }
}
