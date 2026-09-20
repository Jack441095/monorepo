import Foundation
import NiteSubmitCore

func makeDoc(_ pages: [[String]], title: String? = nil, author: String? = nil,
             origin: PDFTextDocument.TextOrigin = .embeddedText) -> PDFTextDocument {
    PDFTextDocument(pageCount: pages.count,
                    pages: pages.enumerated().map {
                        .init(pageNumber: $0.offset + 1, lines: $0.element)
                    },
                    metadataTitle: title, metadataAuthor: author, textOrigin: origin)
}

func runDetectorTests() {
    suite("FieldDetector") {
        let detector = FieldDetector()

        let clear = detector.detect(in: makeDoc([[
            "University of the West of England",
            "Module Leader: Dr Smith",
            "Student Name: Jack Gandy",
            "Student Number: 12345678",
            "Module Code: UFMXYZ-30-3",
            "Module Title: Interactive Audio Systems",
            "Project Title: Interactive Audio Systems",
        ]]))
        eq(clear.studentName.value!, "Jack Gandy", "student name detected")
        check(clear.studentName.confidence == .high, "name HIGH")
        eq(clear.studentId.value!, "12345678", "student id detected")
        check(clear.studentId.confidence == .high, "id HIGH")
        eq(clear.moduleCode.value!, "UFMXYZ-30-3", "module code detected")
        eq(clear.projectTitle.value!, "Interactive Audio Systems", "project title detected")

        let namedDocumentIdentity = detector.checkDocumentIdentity(
            in: makeDoc([[
                "University of Example",
                "Student Name: Jack Gandy",
                "Project Title: Identity Check",
            ]]), policy: .nameRequired)
        check(namedDocumentIdentity.status == .satisfied && !namedDocumentIdentity.isBlocking,
              "name-required policy accepts a name on the first page")
        let missingDocumentIdentity = detector.checkDocumentIdentity(
            in: makeDoc([[
                "University of Example",
                "Project Title: Anonymous Work",
            ]]), policy: .nameRequired)
        check(missingDocumentIdentity.status == .nameMissing && missingDocumentIdentity.isBlocking,
              "name-required policy blocks when the first page has no name")
        let anonymousDocumentIdentity = detector.checkDocumentIdentity(
            in: makeDoc([[
                "University of Example",
                "Student Name: Jack Gandy",
            ]]), policy: .nameProhibited)
        check(anonymousDocumentIdentity.status == .namePresent && anonymousDocumentIdentity.isBlocking,
              "anonymous policy blocks a name found on the first page")
        let laterName = detector.checkDocumentIdentity(
            in: makeDoc([
                ["University of Example", "Project Title: Later Name"],
                ["Body text"],
                ["Student Name: Jack Gandy"],
            ]), policy: .nameRequired)
        check(laterName.status == .nameMissing,
              "document identity check is limited to the first two pages")
        let laterAnonymousName = detector.checkDocumentIdentity(
            in: makeDoc([
                ["University of Example", "Project Title: Anonymous Work"],
                ["Body text"],
                ["Student Name: Jack Gandy"],
            ]), policy: .nameProhibited)
        check(laterAnonymousName.status == .namePresent && laterAnonymousName.isBlocking,
              "anonymous policy blocks an explicit name label on a later page")
        check(laterAnonymousName.evidence.contains("page 3"),
              "anonymous evidence reports the actual later page number")
        let unlabelledBodyName = detector.checkDocumentIdentity(
            in: makeDoc([
                ["University of Example", "Project Title: Anonymous Work"],
                ["The work cites Jack Gandy in its references."],
            ]), policy: .nameProhibited)
        check(unlabelledBodyName.status == .satisfied,
              "anonymous policy does not treat an unlabelled cited name as student identity")
        let laterInlineName = detector.checkDocumentIdentity(
            in: makeDoc([
                ["University of Example", "Project Title: Anonymous Work"],
                ["Body text"],
                ["Author: Jack Gandy"]
            ]), policy: .nameProhibited)
        check(laterInlineName.evidence.contains("page 3"),
              "inline identity evidence reports the actual later page number")
        let noIdentityRule = detector.checkDocumentIdentity(
            in: makeDoc([["Student Name: Jack Gandy"]]), policy: .noRule)
        check(noIdentityRule.status == .notChecked && !noIdentityRule.isBlocking,
              "no-rule identity policy never blocks")

        let simpleCoverName = detector.detect(in: makeDoc([[
            "University of Example",
            "Name: Priya Sharma",
            "Student Number: 50000001",
            "Module Code: ENG2087A",
            "Title: The Ethics of Automated Assessment",
        ]]))
        eq(simpleCoverName.studentName.value!, "Priya Sharma",
           "plain Name label detected on coursework cover")
        check(simpleCoverName.studentName.confidence == .high,
              "plain Name label is HIGH confidence")

        let authorLabel = detector.detect(in: makeDoc([[
            "University of Example",
            "Author: Jane Doe",
            "Title: A Named Coursework Paper",
        ]]))
        eq(authorLabel.studentName.value!, "Jane Doe",
           "Author label detected as student name")
        check(authorLabel.studentName.confidence == .high,
              "Author label is HIGH confidence")

        let candidateLabel = detector.detect(in: makeDoc([[
            "Candidate:",
            "Sam Lee",
            "Assignment Title: Candidate Cover",
        ]]))
        eq(candidateLabel.studentName.value!, "Sam Lee",
           "standalone Candidate label reads the following name line")
        check(candidateLabel.studentName.confidence == .high,
              "standalone Candidate label is HIGH confidence")

        let placeholderName = detector.detect(in: makeDoc([[
            "University of Example",
            "Name: Example Student",
            "Title: Insert your essay title here",
        ]]))
        check(placeholderName.studentName.isMissing,
              "example student placeholder is not treated as a name")
        let splitPlaceholderName = detector.detect(in: makeDoc([[
            "Colorado State University",
            "S here",
            "Example of title page",
        ]]))
        check(splitPlaceholderName.studentName.isMissing,
              "split name placeholder is not treated as a student name")

        let institutionLikeName = detector.detect(in: makeDoc([[
            "Berklee College of Music",
            "The Invisible Carnival: An Ecosystem of Custom Laser Controlled Devices",
            "By",
            "Juan Pablo Gomez",
            "Valencia Campus, Spain",
        ]]))
        eq(institutionLikeName.studentName.value ?? "", "Juan Pablo Gomez",
           "institution/location heading is not offered as a student-name alternative")
        check(!institutionLikeName.studentName.candidates.contains("Valencia Campus, Spain"),
              "campus/location line is excluded from student-name candidates")

        let writtenWorkTitles = detector.detect(in: makeDoc([[
            "University of Example",
            "Student Name: Priya Sharma",
            "Student Number: 50000001",
            "Module Code: ENG2087A",
            "Essay Title: The Ethics of Automated Assessment",
        ]]))
        eq(writtenWorkTitles.projectTitle.value!, "The Ethics of Automated Assessment",
           "essay title label detected")
        check(writtenWorkTitles.projectTitle.confidence == .high,
              "essay title label is HIGH confidence")

        let paperTitle = detector.detect(in: makeDoc([[
            "Student Name: Jack Gandy",
            "Paper Title: Sound Design in Interactive Media",
        ]]))
        eq(paperTitle.projectTitle.value!, "Sound Design in Interactive Media",
           "paper title label detected")

        let sectionHeadings = detector.detect(in: makeDoc([[
            "Berklee College of Music",
            "The Invisible Carnival: An Ecosystem of Custom Laser Controlled Devices",
            "By Juan Pablo Gomez",
            "Abstract iii",
            "Bibliography 24",
        ]]))
        eq(sectionHeadings.projectTitle.value ?? "",
           "The Invisible Carnival: An Ecosystem of Custom Laser Controlled Devices",
           "title heading outranks section headings")
        check(!sectionHeadings.projectTitle.candidates.contains("Abstract iii") &&
              !sectionHeadings.projectTitle.candidates.contains("Bibliography 24"),
              "abstract and bibliography headings are excluded from title candidates")

        let commaOrderedName = detector.detect(in: makeDoc([[
            "University of Example",
            "Student Name: Gomez, Juan Pablo",
            "Project Title: Comma Ordered Cover",
        ]]))
        eq(commaOrderedName.studentName.value!, "Gomez, Juan Pablo",
           "comma-ordered student name detected")
        let commaVariables = commaOrderedName.variableMap()
        eq(commaVariables["first_name"] ?? "", "Juan",
           "comma-ordered first name is derived from the given-name side")
        eq(commaVariables["last_name"] ?? "", "Gomez",
           "comma-ordered last name is derived from the surname side")

        let staff = detector.detect(in: makeDoc([[
            "University of Southampton",
            "Lecturer: Dr Whitfield",
            "Supervisor: Prof. Alvarez",
            "Student Name: Noor Haddad",
            "Student Number: 30000001",
        ]]))
        eq(staff.studentName.value!, "Noor Haddad", "staff name not confused with student")

        let refs = detector.detect(in: makeDoc([[
            "Bath Spa University",
            "Student Name: Chen Wei",
            "Student Number: 40000001",
            "Project Title: Machine Listening Report",
            "References",
            "Smith (2019). Candidate number 55555555 appears here.",
        ]]))
        eq(refs.studentId.value!, "40000001", "reference IDs ignored")

        let none = detector.detect(in: makeDoc([["A page with no fields at all."]]))
        check(none.studentName.isMissing && none.studentName.confidence == .missing,
              "missing stays missing — no hallucination")

        for sid in ["12345678", "A12345678", "24012345", "B09876543"] {
            let m = detector.detect(in: makeDoc([["Student Number: \(sid)"]]))
            eq(m.studentId.value ?? "?", sid, "ID variant \(sid)")
        }
        let splitAlphaId = detector.detect(in: makeDoc([["Student Number: A 12345678"]]))
        eq(splitAlphaId.studentId.value ?? "?", "A12345678",
           "PDF-spaced alphanumeric student number normalised")
        let bad = detector.detect(in: makeDoc([["Student Number: 123"]]))
        check(bad.studentId.isMissing, "non-matching ID format not forced")

        let shortLabelledId = detector.detect(in: makeDoc([["Student Number: 75589"]]))
        eq(shortLabelledId.studentId.value!, "75589",
           "five-digit labelled student number detected")
        check(shortLabelledId.studentId.confidence == .high,
              "five-digit labelled student number remains HIGH")

        let alternateIdLabel = detector.detect(in: makeDoc([["Matriculation No: 12345"]]))
        eq(alternateIdLabel.studentId.value!, "12345",
           "matriculation number label detected")

        // Two-letter ID prefix: previously only a single leading letter was accepted
        // (studentIdPatterns/labelledStudentIdPatterns both only had `[A-Z]\d{7,9}`).
        let twoLetterPrefixId = detector.detect(in: makeDoc([["Student Number: AB1234567"]]))
        eq(twoLetterPrefixId.studentId.value ?? "?", "AB1234567",
           "two-letter-prefix student ID now detected")

        // US-centric label synonyms that weren't in the original UK/exam-board-centric lists.
        let usLabelId = detector.detect(in: makeDoc([["Roll Number: 87654321"]]))
        eq(usLabelId.studentId.value ?? "?", "87654321", "\"roll number\" label detected")
        let bannerIdDoc = detector.detect(in: makeDoc([["Banner ID: 900123456"]]))
        eq(bannerIdDoc.studentId.value ?? "?", "900123456", "\"banner id\" label detected")
        let courseNumberDoc = detector.detect(in: makeDoc([["Course Number: CS3245"]]))
        eq(courseNumberDoc.moduleCode.value ?? "?", "CS3245", "\"course number\" label detected")

        // Candidate number previously reused the same tight pattern set regardless of being
        // right after an explicit label — a short (3-digit) candidate number, a real shape some
        // exam boards use, silently dropped to .missing even with a clear label right next to it.
        let shortCandidateNumber = detector.detect(in: makeDoc([["Candidate Number: 007"]]))
        eq(shortCandidateNumber.candidateNumber.value ?? "?", "007",
           "three-digit labelled candidate number now detected")

        // Mononym: a single-word name is now accepted right after an explicit label (isPlausiblePerson's
        // default two-word minimum exists for the weaker unlabelled/inferred path, not this one).
        let mononym = detector.detect(in: makeDoc([["Student Name: Madonna", "Student Number: 12345678"]]))
        eq(mononym.studentName.value ?? "?", "Madonna", "labelled mononym now detected")
        check(mononym.studentName.confidence == .high, "labelled mononym is HIGH confidence")
        // Safety guard: the single-word allowance is title-case only, so an all-caps placeholder
        // like "TBD" (which would otherwise pass every other character-class check) still misses.
        let tbdPlaceholder = detector.detect(in: makeDoc([["Student Name: TBD", "Student Number: 12345678"]]))
        check(tbdPlaceholder.studentName.isMissing, "all-caps single-word placeholder is not treated as a name")

        let distinctIdentifiers = detector.detect(in: makeDoc([[
            "Student Number: 00361288",
            "Candidate Number: 004812",
            "Assignment Code: MEX4E001R~001",
        ]]))
        eq(distinctIdentifiers.studentId.value!, "00361288",
           "student number preserves leading zeroes")
        eq(distinctIdentifiers.candidateNumber.value!, "004812",
           "candidate number is detected separately")
        check(distinctIdentifiers.studentId.value != distinctIdentifiers.candidateNumber.value,
              "candidate number is not silently substituted for student number")
        eq(distinctIdentifiers.assignmentCode.value!, "MEX4E001R~001",
           "assignment code preserves institution punctuation")

        let grouped = detector.detect(in: makeDoc([[
            "Group ID: G-17",
            "Student Name: Jane Doe",
            "Student Name: Sam Lee",
            "Project Title: Shared Research Project",
        ]]))
        eq(grouped.groupId.value!, "G-17", "labelled group ID detected")
        check(grouped.groupId.confidence == .high, "labelled group ID is HIGH confidence")

        let namesWithoutGroupId = detector.detect(in: makeDoc([[
            "Student Name: Jane Doe",
            "Student Name: Sam Lee",
            "Project Title: Shared Research Project",
        ]]))
        check(namesWithoutGroupId.groupId.isMissing,
              "multiple student names do not invent a group ID")

        let abbreviatedAssignment = detector.detect(in: makeDoc([[
            "Assignment No.: HEA3183",
        ]]))
        eq(abbreviatedAssignment.assignmentCode.value!, "HEA3183",
           "Assignment No. label is detected as an assignment code")

        let assessmentNumber = detector.detect(in: makeDoc([[
            "Assessment Number: MEX4E001R~002",
        ]]))
        eq(assessmentNumber.assignmentCode.value!, "MEX4E001R~002",
           "Assessment Number label is detected as an assignment code")

        let candidateOnly = detector.detect(in: makeDoc([[
            "Candidate Number: 004812",
        ]]))
        check(candidateOnly.studentId.isMissing,
              "candidate-only submission does not invent a student number")
        eq(candidateOnly.candidateNumber.value!, "004812",
           "candidate-only submission remains usable anonymously")

        let abbreviatedCandidate = detector.detect(in: makeDoc([[
            "Candidate No.: A12345678",
        ]]))
        check(abbreviatedCandidate.studentId.isMissing,
              "abbreviated candidate number does not become a student number")
        eq(abbreviatedCandidate.candidateNumber.value!, "A12345678",
           "Candidate No. label is detected separately")

        let ocr = detector.detect(in: makeDoc([[
            "Student Number: 00361288",
            "Project Title: OCR Cover",
        ]], origin: .ocr))
        eq(ocr.studentId.value!, "00361288", "OCR student number detected")
        check(ocr.studentId.confidence == .medium,
              "OCR detections are capped at MEDIUM for review")
        check(ocr.studentId.source?.hasPrefix("OCR:") == true,
              "OCR evidence is visible in the detection source")

        for code in ["CS101", "MUSC4001", "UFMXYZ-30-3", "ENG2087A"] {
            let m = detector.detect(in: makeDoc([["Module Code: \(code)"]]))
            eq(m.moduleCode.value ?? "?", code, "module format \(code)")
        }

        let unlabelledModule = detector.detect(in: makeDoc([[
            "University of Example",
            "CS101",
            "Student Name: Noor Haddad",
        ]]))
        eq(unlabelledModule.moduleCode.value!, "CS101",
           "unlabelled module-shaped token surfaced")
        check(unlabelledModule.moduleCode.confidence == .low,
              "unlabelled module-shaped token remains LOW")

        let multi = detector.detect(in: makeDoc([[
            "Cardiff University",
            "Assignment Title: First Option",
            "Assessment Title: Second Option",
            "Student Name: Priya Sharma",
            "Student Number: 50000001",
        ]]))
        check(!multi.projectTitle.candidates.isEmpty, "candidates surfaced when ambiguous")

        let meta = detector.detect(in: makeDoc([["References and appendices only"]],
                                               title: "Metadata Title Here"))
        if let t = meta.projectTitle.value {
            eq(t, "Metadata Title Here", "metadata title used as last resort")
            check(meta.projectTitle.confidence == .low, "metadata title is LOW confidence only")
        } else {
            check(meta.projectTitle.isMissing, "metadata-only doc has no confident title")
        }

        let uni = detector.detect(in: makeDoc([[
            "University of the West of England",
            "Student Name: Zoë Müller",
            "Student Number: 66778899",
        ]]))
        eq(uni.studentName.value!, "Zoë Müller", "Unicode names preserved")

        // Cover sheets in the real corpus often have a name but no label.
        // This must remain MEDIUM so the owner reviews it before renaming.
        let titlePage = detector.detect(in: makeDoc([[
            "Ashesi University",
            "SMART WATER METERING AND QUALITY MONITORING",
            "Alex Waweru",
            "A thesis submitted in partial fulfilment of the requirements for the degree",
        ]]))
        eq(titlePage.studentName.value!, "Alex Waweru", "unlabelled title-page name detected")
        check(titlePage.studentName.confidence == .medium, "title-page name capped at MEDIUM")
        eq(titlePage.studentName.rule ?? "", "title_page_student_name", "title-page name rule")
        eq(titlePage.projectTitle.value!, "SMART WATER METERING AND QUALITY MONITORING",
           "title-page heading detected")
        check(titlePage.projectTitle.confidence == .medium, "title-page title capped at MEDIUM")

        let titleOnly = detector.detect(in: makeDoc([[
            "University of Cambridge",
            "An Ecosystem of Custom Laser Controlled Devices",
            "A thesis submitted in partial fulfilment of the requirements for the degree",
        ]]))
        eq(titleOnly.projectTitle.value!, "An Ecosystem of Custom Laser Controlled Devices",
           "title-page title survives without a name")
        check(titleOnly.studentName.isMissing, "title-like line is not hallucinated as a name")

        let bareName = detector.detect(in: makeDoc([["Alex Waweru"]]))
        check(bareName.studentName.isMissing, "bare body name remains missing without title context")

        let genericAcademicLabel = detector.detect(in: makeDoc([[
            "Berklee College",
            "Final Paper",
            "An Ecosystem of Custom Laser Controlled Devices",
            "Master of Music",
        ]]))
        check(genericAcademicLabel.studentName.isMissing,
              "generic academic label is not treated as a student name")

        let guidance = detector.detect(in: makeDoc([[
            "University of Washington",
            "MS Capstone Report Format Guidelines",
            "Title page",
            "Font: Any legible font except script, italic, or ornamental fonts",
            "Times New Roman.",
            "Temporary Policy",
        ]]))
        check(guidance.studentName.isMissing,
              "guidance headings are not treated as a student name")
        check(guidance.projectTitle.value != "Font: Any legible font except script, italic, or ornamental fonts",
              "font guidance is not treated as a project title")
        let guidanceClassification = detector.classifyDocument(in: makeDoc([[
            "University of Washington",
            "MS Capstone Report Format Guidelines",
            "Title page",
            "Font: Any legible font except script, italic, or ornamental fonts",
        ]]))
        check(guidanceClassification.kind == .guidanceTemplate,
              "guidance document is classified for review context")

        let coverSheetGuidance = detector.classifyDocument(in: makeDoc([[
            "Please use a separate cover sheet for each piece of work, ensuring that the cover sheet is merged with",
            "LastName_FirstName_UCASpersonalID_DocumentName",
        ]]))
        check(coverSheetGuidance.kind == .guidanceTemplate,
              "cover-sheet instructions are classified for review context")

        let thesisExampleGuidance = detector.classifyDocument(in: makeDoc([[
            "Example of thesis title page",
            "Date of submission for examination (month and year)",
        ]]))
        check(thesisExampleGuidance.kind == .guidanceTemplate,
              "thesis title-page examples are classified for review context")

        let researchGuidance = detector.classifyDocument(in: makeDoc([[
            "The student's research project must be based on a topic that has been approved",
            "The report should be written in a serious and matter-of-fact tone",
        ]]))
        check(researchGuidance.kind == .guidanceTemplate,
              "research-project instructions are classified for review context")

        let submissionClassification = detector.classifyDocument(in: makeDoc([[
            "University of Example",
            "Name: Priya Sharma",
            "Student Number: 50000001",
            "Essay Title: The Ethics of Automated Assessment",
        ]]))
        check(submissionClassification.kind == .likelySubmission,
              "ordinary coursework is not classified as guidance")

        let guidanceLabels = detector.detect(in: makeDoc([[
            "University of Colorado Anschutz Medical Campus",
            "BE DESCRIPTIVE",
            "References Cited",
            "CAPSTONE FINAL REPORT",
        ]]))
        check(guidanceLabels.studentName.isMissing,
              "guidance section labels are not treated as a student name")
        check(guidanceLabels.projectTitle.value?.lowercased() != "be descriptive",
              "generic guidance instruction is not treated as a project title")

        let checklistHeading = detector.detect(in: makeDoc([[
            "Edge Hill University",
            "Module No: HEA3183",
            "Assignment Title: Submission Checklist",
            "Name: Student Name",
        ]]))
        check(checklistHeading.projectTitle.isMissing,
              "submission checklist guidance is not treated as a project title")

        let byline = detector.detect(in: makeDoc([[
            "Berklee College of Music",
            "Final Paper",
            "An Ecosystem of Custom Laser Controlled Devices",
            "by Juan Pablo Gomez",
            "Master of Music",
        ]]))
        eq(byline.studentName.value!, "Juan Pablo Gomez", "unlabelled byline name detected")
        check(byline.studentName.confidence == .medium, "byline name capped at MEDIUM")

        let supervisorThenByline = detector.detect(in: makeDoc([[
            "Berklee College of Music",
            "The Invisible Carnival:",
            "An Ecosystem of Custom Laser Controlled Devices",
            "Final Paper",
            "Submitted in Partial Fulfillment of the Degree of",
            "Master of Music in Production, Technology, and Innovation",
            "Supervisor: Nacho Marco, Marta Verde",
            "by Juan Pablo Gomez",
            "Valencia Campus, Spain",
            "December 2020",
        ]]))
        eq(supervisorThenByline.studentName.value!, "Juan Pablo Gomez",
           "explicit byline wins after supervisor")
        eq(supervisorThenByline.projectTitle.value!,
           "The Invisible Carnival: An Ecosystem of Custom Laser Controlled Devices",
           "Berklee cover title recombined")

        let splitCover = detector.detect(in: makeDoc([
            [
                "DEVELOPMENT OF A",
                "THERMOELECTRIC GENERATOR SYSTEM",
                "FOR IOT APPLICATIONS",
                "WONG WEN KANG",
                "Universiti Tunku Abdul Rahman",
            ],
            [
                "DEVELOPMENT OF A",
                "THERMOELECTRIC GENERATOR SYSTEM",
                "FOR IOT APPLICATIONS",
                "WONG WEN KANG",
                "A project report submitted in partial fulfilment of the requirements",
            ],
        ]))
        eq(splitCover.studentName.value!, "WONG WEN KANG", "uppercase cover name detected")
        eq(splitCover.projectTitle.value!, "DEVELOPMENT OF A THERMOELECTRIC GENERATOR SYSTEM FOR IOT APPLICATIONS",
           "split uppercase title recombined")

        let explicitByline = detector.detect(in: makeDoc([[
            "NORTHERN ILLINOIS UNIVERSITY",
            "BACKGROUND CORRECTIONS USING ELECTROTHERMAL",
            "VAPORIZATION INDUCTIVELY COUPLED PLASMA",
            "WITH AN ULTRAVIOLET ACOUSTO-OPTIC",
            "TUNABLE FILTER",
            "BY",
            "KELLEN LEE HUNTER",
            "A THESIS SUBMITTED TO THE GRADUATE SCHOOL",
        ]]))
        eq(explicitByline.studentName.value!, "KELLEN LEE HUNTER",
           "explicit BY marker outranks uppercase title lines")
        eq(explicitByline.projectTitle.value!,
           "BACKGROUND CORRECTIONS USING ELECTROTHERMAL VAPORIZATION INDUCTIVELY COUPLED PLASMA WITH AN ULTRAVIOLET ACOUSTO-OPTIC TUNABLE FILTER",
           "uppercase title block recombined before explicit byline")

        let templatePlaceholder = detector.detect(in: makeDoc([[
            "EXAMPLE OF TITLE PAGE FOR MASTER’S THESIS",
            "TITLE IN CAPITAL LETTERS AND DOUBLE",
            "SPACED IF MORE THAN ONE LINE",
            "Submitted by",
            "Student’s Name",
            "Colorado State University",
            "Spring 2014",
        ]]))
        check(templatePlaceholder.studentName.isMissing,
              "template placeholder is not treated as a student name")
        check(templatePlaceholder.projectTitle.isMissing,
              "template title instructions are not treated as a project title")

        let graduateCollege = detector.detect(in: makeDoc([[
            "Sample Thesis Title Page",
            "The Graduate College at the University of Nebraska",
        ]]))
        eq(graduateCollege.university.value!, "University of Nebraska",
           "awarding university outranks graduate-college wrapper")

        let repositoryWrapper = detector.detect(in: makeDoc([
            [
                "This electronic thesis or dissertation has been downloaded from the King's Research Portal",
                "Deception",
                "END USER LICENCE AGREEMENT",
            ],
            [
                "Deception",
                "By",
                "S tefan Sarkadi",
                "A thesis submitted in fulfilment for the degree of Doctor of Philosophy",
            ],
        ]))
        eq(repositoryWrapper.studentName.value!, "Stefan Sarkadi", "split repository byline detected")
        eq(repositoryWrapper.projectTitle.value!, "Deception", "repository title survives licence wrapper")

        let genericThesisBanner = detector.detect(in: makeDoc([[
            "The University of Sheffield",
            "DOCTORAL THESIS Reconstruction of Soil Stress-Strain Response Using Optimisation",
            "Author: Jared A CHARLES Supervisors: Dr Example",
        ]]))
        eq(genericThesisBanner.projectTitle.value!,
           "Reconstruction of Soil Stress-Strain Response Using Optimisation",
           "generic doctoral-thesis banner is removed from title")

        let asheshiGuidance = detector.detect(in: makeDoc([[
            "ASHESI UNIVERSITY",
            "Alex Waweru",
            "The Ashesi brand and logo are integral parts of our worldwide image and identity.",
            "This guide has been developed to help you clearly understand our policies towards the use of the Ashesi brand.",
        ]]))
        check(asheshiGuidance.projectTitle.isMissing,
              "branding guidance is not treated as a project title")

        let labelledAuthorWithSupervisors = detector.detect(in: makeDoc([[
            "The University of Sheffield",
            "Reconstruction of Soil Stress-Strain Response Using Optimisation Author: Jared A CHARLES Supervisors: Dr Example",
            "A thesis submitted in partial fulfilment of the requirements for the degree of Doctor of Philosophy",
        ]]))
        eq(labelledAuthorWithSupervisors.studentName.value ?? "<missing>", "Jared A CHARLES",
           "author line is separated from supervisor text")
        eq(labelledAuthorWithSupervisors.projectTitle.value!,
           "Reconstruction of Soil Stress-Strain Response Using Optimisation",
           "title-page author marker is removed from title")
        eq(labelledAuthorWithSupervisors.university.value!, "The University of Sheffield",
           "full university name is not truncated to The University")

        let institutionVariants = detector.detect(in: makeDoc([[
            "Universiti Tunku Abdul Rahman",
            "Student Name: Lau Wei Qing",
            "Project Title: Smartphone Usage Parental Monitoring & Control",
        ]]))
        eq(institutionVariants.university.value!, "Universiti Tunku Abdul Rahman",
           "Universiti institution heading detected")

        let extendedInstitution = detector.detect(in: makeDoc([[
            "Berklee College of Music Valencia Campus",
            "Student Name: Juan Pablo Gomez",
        ]]))
        eq(extendedInstitution.university.value!, "Berklee College of Music Valencia Campus",
           "college and campus suffix retained")

        let contextualInstitution = detector.detect(in: makeDoc([[
            "Thesis submitted to the University of Sheffield in fulfilment of the degree",
            "University of Sheffield",
        ]]))
        eq(contextualInstitution.university.value!, "University of Sheffield",
           "contextual submission sentence does not outrank institution heading")

        let hyphenatedInstitution = detector.detect(in: makeDoc([[
            "American International University - Bangladesh",
        ]]))
        eq(hyphenatedInstitution.university.value!, "American International University - Bangladesh",
           "hyphenated university suffix retained")

        let titleWithByMarker = detector.detect(in: makeDoc([[
            "University of Sheffield",
            "Knowledge Evolution in Social Media: Understanding the Effects of Website Designs on the Selection of User-Generated Content By:",
            "Gabriela Morales Martinez",
            "A thesis submitted for the degree of Doctor of Philosophy",
        ]]))
        eq(titleWithByMarker.projectTitle.value!,
           "Knowledge Evolution in Social Media: Understanding the Effects of Website Designs on the Selection of User-Generated Content",
           "title-page By marker is removed")

        let longTitle = detector.detect(in: makeDoc([[
            "A Temple Unabridged with Priceless Treasure: An",
            "Investigation of Yorkshire Public Libraries as Intellectual",
            "Sanctuary During the First World War: 1914-1918",
            "Molly Alyssa Newcomb",
            "Thesis submitted to the University of Sheffield",
        ]]))
        eq(longTitle.studentName.value!, "Molly Alyssa Newcomb",
           "long thesis title cover name detected")
        eq(longTitle.projectTitle.value!,
           "A Temple Unabridged with Priceless Treasure: An Investigation of Yorkshire Public Libraries as Intellectual Sanctuary During the First World War: 1914-1918",
           "long thesis title recombined without truncation")

        let groupCover = detector.detect(in: makeDoc([[
            "SMART WATER METERING AND QUALITY MONITORING",
            "1. Majid, Abdul ID: 19-40877-2 Dept: EEE",
            "2. Islam, MD.Ashikul ID: 19-40843-2 Dept: EEE",
            "Under the Supervision",
            "Abir Ahmed",
            "Assistant Professor",
            "American International University - Bangladesh",
        ]]))
        eq(groupCover.studentName.value!, "Majid Abdul", "group student name preferred over supervisor")
        check(groupCover.studentName.candidates.contains("Islam MD.Ashikul"),
              "group student alternatives surfaced")

        let labelledTitle = detector.detect(in: makeDoc([[
            "University of Chicago",
            "Title: Deception",
            "Student ID: 12345678",
        ]]))
        eq(labelledTitle.projectTitle.value!, "Deception", "plain Title label detected")

        let missouriTitlePage = detector.detect(in: makeDoc([[
            "A STUDY OF HEALTH CARE",
            "DELIVERY COSTS",
            "A Thesis",
            "presented to",
            "the Faculty of the Graduate School",
            "at the University of Missouri-Columbia",
            "In Partial Fulfillment of the Requirements for the Degree",
            "Master of Arts",
            "by",
            "CAROLYN HEYMEYER",
            "Dr. Larry Jaloweic, Thesis Supervisor",
        ]]))
        eq(missouriTitlePage.projectTitle.value!,
           "A STUDY OF HEALTH CARE DELIVERY COSTS",
           "Missouri title-page title outranks presented-to prose")

        let illinoisTitlePage = detector.detect(in: makeDoc([[
            "Coffee Consumption of Graduate Students Trying to Finish Dissertations",
            "by",
            "Anne E. Garvie",
            "Dissertation",
            "Submitted in partial fulfillment of the requirements",
            "for the degree of Doctor of Philosophy in Food Science and Human Nutrition",
            "in the Graduate College of the",
            "University of Illinois Urbana-Champaign, 2026",
            "Doctoral Committee:",
            "Professor Laurence Strongarm, Chair",
            "Professor Joseph Green, Director of Research",
        ]]))
        eq(illinoisTitlePage.projectTitle.value!,
           "Coffee Consumption of Graduate Students Trying to Finish Dissertations",
           "Illinois title-page title preserves academic wording")
        eq(illinoisTitlePage.university.value!, "University of Illinois Urbana-Champaign",
           "Illinois awarding university outranks Graduate College wrapper")
    }
}
