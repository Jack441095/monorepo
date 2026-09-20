import Foundation

/// Deterministic, label-driven field extraction over a `PDFTextDocument`.
/// Precision is prioritised over recall: a missing value is always preferred
/// to a confidently wrong one.
public struct FieldDetector: Sendable {
    public struct Config: Sendable {
        public var studentIdPatterns: [String] = [
            #"^\d{6,10}$"#,
            #"^[A-Z]\d{7,9}$"#,
            #"^[A-Z]{2}\d{6,8}$"#,
            #"^\d{2}[A-Z]\d{4,8}$"#,
            #"^[A-Za-z]\d{5}[A-Za-z]$"#,
            #"^[A-Z0-9]{3}[- ]?\d{5,7}$"#
        ]
        /// A labelled student-number field is stronger evidence than an
        /// unlabelled number-shaped token. Some institutions use five-digit
        /// student numbers, so the labelled path deliberately accepts that
        /// form while the unlabelled fallback remains stricter.
        public var labelledStudentIdPatterns: [String] = [
            #"^\d{5,12}$"#,
            #"^[A-Z]\d{7,9}$"#,
            #"^[A-Z]{2}\d{6,8}$"#,
            #"^\d{2}[A-Z]\d{4,8}$"#,
            #"^[A-Za-z]\d{5}[A-Za-z]$"#,
            #"^[A-Z0-9]{3}[- ]?\d{5,7}$"#
        ]
        /// Candidate number has no unlabelled fallback path (detectCandidateNumber only ever
        /// looks right after an explicit label), so there is just one pattern set here — widened
        /// versus a hypothetical strict/unlabelled set the same way labelledStudentIdPatterns
        /// widens over studentIdPatterns, since some exam boards use short (3-digit) candidate
        /// numbers or slightly longer numeric IDs.
        public var labelledCandidateNumberPatterns: [String] = [
            #"^\d{3,12}$"#,
            #"^[A-Z0-9][A-Z0-9-]{3,14}$"#
        ]
        public init() {}
    }

    public var config: Config
    public init(config: Config = Config()) { self.config = config }

    // MARK: - Label tables

    static let studentNameLabels = ["student name", "name of student", "candidate name",
                                    "submitted by", "author", "candidate", "name"]
    static let staffKeywords = [
        "lecturer", "supervisor", "module leader", "tutor", "professor",
        "prof.", "dr ", "mr ", "mrs ", "ms ", "marker",
        "second marker", "examiner", "instructor", "coordinator"
    ]
    static let studentIdLabels = [
        "student number", "student id", "student no",
        "registration number", "matriculation number", "matriculation no",
        "enrolment number", "enrollment number", "university id",
        "student reference", "id number",
        // US-centric phrasing — the original label list was exam-board/UK-centric.
        "roll number", "banner id", "campus id"
    ]
    static let candidateNumberLabels = [
        "candidate number", "exam candidate number", "examination candidate number",
        "candidate no", "exam candidate no", "examination candidate no",
        "anonymous marking number"
    ]
    static let assignmentCodeLabels = [
        "assignment code", "assessment code", "coursework code", "assessment reference",
        "assignment number", "assignment no", "assessment number", "assessment no",
        "coursework number", "coursework no"
    ]
    static let groupIdLabels = [
        "group id", "group number", "group name", "team id", "team number", "team name"
    ]
    static let moduleLabels = ["module code", "module", "unit code", "unit", "course code",
                               "course number"]
    static let moduleTitleLabels = ["module title", "module name", "unit title"]
    static let projectLabels = [
        "project title", "assignment title", "assessment title",
        "essay title", "paper title", "work title", "dissertation title",
        "thesis title", "project", "assignment", "assessment", "report title"
    ]
    static let universityLabels = ["university", "institution", "school", "faculty"]

    // MARK: - Public API

    public func detect(in doc: PDFTextDocument) -> SubmissionMetadata {
        var meta = SubmissionMetadata()
        meta.studentId = detectStudentId(in: doc)
        meta.candidateNumber = detectCandidateNumber(in: doc)
        meta.assignmentCode = detectAssignmentCode(in: doc)
        meta.groupId = detectGroupId(in: doc)
        meta.studentName = detectStudentName(in: doc)
        meta.moduleCode = detectModuleCode(in: doc)
        meta.moduleTitle = detectModuleTitle(in: doc)
        meta.university = detectUniversity(in: doc)
        meta.projectTitle = detectProjectTitle(in: doc)
        if doc.textOrigin == .ocr {
            meta.studentName = ocrDetection(meta.studentName)
            meta.studentId = ocrDetection(meta.studentId)
            meta.candidateNumber = ocrDetection(meta.candidateNumber)
            meta.assignmentCode = ocrDetection(meta.assignmentCode)
            meta.university = ocrDetection(meta.university)
            meta.moduleCode = ocrDetection(meta.moduleCode)
            meta.moduleTitle = ocrDetection(meta.moduleTitle)
            meta.projectTitle = ocrDetection(meta.projectTitle)
        }
        return meta
    }

    func ocrDetection(_ detection: Detection) -> Detection {
        guard !detection.isMissing else { return detection }
        let confidence: Confidence = detection.confidence == .high ? .medium : detection.confidence
        let source = detection.source.map { "OCR: \($0)" } ?? "Detected from OCR text — please check"
        return Detection(value: detection.value, confidence: confidence,
                         source: source,
                         rule: detection.rule.map { "ocr_\($0)" },
                         candidates: detection.candidates)
    }

    // MARK: - Student ID

    func detectStudentId(in doc: PDFTextDocument) -> Detection {
        for hit in findLabels(Self.studentIdLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if let v = matchingIdentifier(tail, patterns: config.labelledStudentIdPatterns) {
                return Detection(value: v, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_student_id")
            }
        }
        for line in firstLines(doc, count: 25) {
            if let v = matchingId(line) {
                return Detection(value: v, confidence: .medium,
                                 source: "Detected ID-formatted text on page 1 — please check",
                                 rule: "pattern_student_id")
            }
        }
        return .missing("No confident student number found")
    }

    func detectCandidateNumber(in doc: PDFTextDocument) -> Detection {
        for hit in findLabels(Self.candidateNumberLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if let value = matchingIdentifier(tail, patterns: config.labelledCandidateNumberPatterns) {
                return Detection(value: value, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_candidate_number")
            }
        }
        return .missing("No labelled candidate number found")
    }

    func matchingId(_ s: String) -> String? {
        matchingIdentifier(s, patterns: config.studentIdPatterns)
    }

    func matchingIdentifier(_ s: String, patterns: [String]) -> String? {
        let trimmed = s.trimmingCharacters(in: CharacterSet.punctuationCharacters.union(.whitespaces))
        guard !trimmed.isEmpty else { return nil }
        // Some PDF text layers insert a space after the leading letter in an
        // alphanumeric student number (for example `A 12345678`). Keep the
        // original exact candidate first, then try the unambiguous compact
        // form. Other internal spacing is deliberately not removed.
        let compactLeadingLetter = trimmed.replacingOccurrences(
            of: #"^([A-Za-z])\s+(\d)"#, with: "$1$2", options: .regularExpression)
        let candidates = compactLeadingLetter == trimmed ? [trimmed] : [trimmed, compactLeadingLetter]
        for candidate in candidates {
            for pattern in patterns {
                guard let re = try? NSRegularExpression(pattern: pattern) else { continue }
                let nsrange = NSRange(candidate.startIndex..., in: candidate)
                if let m = re.firstMatch(in: candidate, range: nsrange),
                   m.range.location == 0 && m.range.length == (candidate as NSString).length {
                    return candidate
                }
            }
        }
        return nil
    }

    // MARK: - Assignment code

    func detectAssignmentCode(in doc: PDFTextDocument) -> Detection {
        for hit in findLabels(Self.assignmentCodeLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if let value = assignmentCodeToken(in: tail) {
                return Detection(value: value, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_assignment_code")
            }
        }
        return .missing("No labelled assignment code found")
    }

    func assignmentCodeToken(in value: String) -> String? {
        let pattern = #"[A-Za-z0-9][A-Za-z0-9~_-]{1,30}"#
        guard let match = value.firstMatch(pattern) else { return nil }
        return match
    }

    // MARK: - Group identifier

    /// Group identity is accepted only when the document labels it explicitly.
    /// Multiple detected student names are deliberately not collapsed into a
    /// guessed group filename component.
    func detectGroupId(in doc: PDFTextDocument) -> Detection {
        for hit in findLabels(Self.groupIdLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if isPlausibleGroupIdentifier(tail) {
                return Detection(value: tail, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_group_id")
            }
        }
        return .missing("No labelled group identifier found; enter one manually for group filenames")
    }

    func isPlausibleGroupIdentifier(_ raw: String) -> Bool {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.count <= 80,
              !value.contains("@"), !value.contains("/"), !value.contains("\\") else { return false }
        let lower = value.lowercased()
        let placeholders = ["group", "group name", "group id", "team", "team name", "team id",
                            "enter group", "your group", "example group"]
        guard !placeholders.contains(lower), !lower.contains("enter your") else { return false }
        return value.range(of: #"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$"#, options: .regularExpression) != nil
    }


    // MARK: - Student Name

    func detectStudentName(in doc: PDFTextDocument) -> Detection {
        var candidates: [(String, Int)] = []
        for hit in findLabels(Self.studentNameLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if isPlausiblePerson(tail, allowSingleWord: true) { candidates.append((tail, hit.page.pageNumber)) }
        }
        // Thesis and coursework covers sometimes put an explicit name label on
        // its own line, followed by the value on the next line. Accept only an
        // exact label line here; this prevents ordinary prose beginning with
        // words such as “author” or “candidate” from becoming identity data.
        let orderedLabels = Self.studentNameLabels.sorted { $0.count > $1.count }
        for page in doc.pages.prefix(3) {
            for index in page.lines.indices {
                let line = page.lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
                let lower = line.lowercased()
                guard let label = orderedLabels.first(where: {
                    lower == $0 || lower == "\($0):" || lower == "\($0) :"
                }), index + 1 < page.lines.count else { continue }
                let value = page.lines[index + 1].trimmingCharacters(in: .whitespacesAndNewlines)
                guard isPlausiblePerson(value, allowSingleWord: true), !candidates.contains(where: { $0.0 == value }) else { continue }
                candidates.append((value, page.pageNumber))
                _ = label // Keep the exact-label match explicit for readability.
            }
        }
        if let best = candidates.first {
            let conf: Confidence = candidates.count == 1 ? .high : .medium
            let rule = candidates.count == 1 ? "label_student_name" : "label_student_name_ambiguous"
            let sourceNote = candidates.count == 1
                ? "Found after a name label on page \(best.1)"
                : "Multiple candidate names found (possible group submission) — please check"
            return Detection(value: best.0, confidence: conf,
                             source: sourceNote,
                             rule: rule,
                             candidates: candidates.map(\.0))
        }

        if let titlePageName = detectTitlePageStudentName(in: doc) {
            return titlePageName
        }
        return .missing("No labelled or title-page student name found")
    }

    /// `allowSingleWord` is only set by the labelled-name detection path in detectStudentName —
    /// an explicit "Student Name:" label is strong enough evidence to accept a mononym (e.g.
    /// "Madonna"), which the default two-word minimum exists to filter out of the unlabelled/
    /// inferred title-page path, where a single stray capitalized word is a much weaker signal.
    /// Still gated to title-case only (first letter upper, rest lower) so an all-caps placeholder
    /// like "TBD" can't slip through just because it satisfies the character-class check below.
    func isPlausiblePerson(_ s: String, allowSingleWord: Bool = false) -> Bool {
        let wordCount = s.split(separator: " ").count
        if wordCount < 2 {
            guard allowSingleWord, wordCount == 1, s.count <= 60,
                  s.first?.isUppercase == true, s.dropFirst().allSatisfy({ !$0.isLetter || $0.isLowercase })
            else { return false }
        }
        guard s.count <= 60 else { return false }
        let commaParts = s.split(separator: ",", omittingEmptySubsequences: false)
        guard commaParts.count <= 2,
              commaParts.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            return false
        }
        let lower = s.lowercased()
        let normalized = lower.replacingOccurrences(of: "’", with: "'")
        let placeholderPhrases = [
            "student name", "student's name", "candidate name", "your name",
            "full name", "name here", "author name", "example name", "example student"
        ]
        if placeholderPhrases.contains(where: { normalized.contains($0) }) { return false }
        // Some extracted template placeholders split “Name here” into a
        // single initial plus the word “here” (for example “S here”). Keep
        // that instructional text out without rejecting legitimate initials
        // such as “S Lee”.
        if normalized.range(of: #"^[a-z]\s+here$"#, options: .regularExpression) != nil {
            return false
        }
        if Self.staffKeywords.contains(where: { lower.contains($0) }) { return false }
        if s.contains("@") || s.contains("/") { return false }
        return s.range(of: #"^[A-Za-zÀ-ɏ'’\-\., ]+$"#, options: .regularExpression) != nil
    }

    /// Conservative fallback for cover sheets that show an author/name but
    /// omit a machine-readable label. A name-shaped line is accepted only on
    /// the first two pages and only when the pages also look like an academic
    /// title block. Page 2 covers handle repository wrappers on page 1.
    func detectTitlePageStudentName(in doc: PDFTextDocument) -> Detection? {
        guard !doc.pages.isEmpty else { return nil }
        let lines = Array(doc.pages.prefix(2).flatMap(\.lines).prefix(80))
        let pageText = lines.joined(separator: " ").lowercased()
        let contextWords = ["university", "college", "faculty", "school", "department",
                            "thesis", "dissertation", "project", "degree", "bachelor",
                            "master", "doctor", "submitted", "programme", "program",
                            "author", "candidate", "supervisor", "title", "universiti",
                            "report", "application"]
        let hasNameCandidate = lines.indices.contains {
            titlePagePersonValue(in: lines, at: $0) != nil
        }
        let hasHeadingCandidate = lines.contains {
            let value = $0.trimmingCharacters(in: .whitespacesAndNewlines)
            return titlePagePersonValue(value) == nil &&
                titlePageTitleValue(value) != nil &&
                !isTitlePageInstitutionLine(value)
        }
        guard contextWords.contains(where: { pageText.contains($0) }) ||
            (hasNameCandidate && hasHeadingCandidate) else { return nil }

        var candidates: [String] = []
        var explicitCandidates: [String] = []
        for (index, line) in lines.enumerated() {
            let lowerLine = line.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let values = titlePagePersonValues(in: lines, at: index)
            for value in values where !candidates.contains(value) {
                let previous = index > 0 ? lines[index - 1].lowercased() : ""
                let next = index + 1 < lines.count ? lines[index + 1].lowercased() : ""
                let explicitAuthorMarker = lowerLine == "by" || lowerLine == "by:" || lowerLine.hasPrefix("by ") ||
                    lowerLine.hasPrefix("author ") || lowerLine.hasPrefix("author:") ||
                    lowerLine.hasPrefix("written by ") || lowerLine.hasPrefix("written by:")
                let staffContext = !explicitAuthorMarker && (previous.contains("supervis") ||
                    previous.contains("advisor") || previous.contains("lecturer") ||
                    previous.contains("committee") || previous.contains("member") ||
                    previous.contains("example") || next.contains("professor") ||
                    next.contains("lecturer") || next.contains("committee") ||
                    next.contains("member"))
                if explicitAuthorMarker {
                    if !explicitCandidates.contains(value) { explicitCandidates.append(value) }
                } else if !staffContext,
                          !isTitlePageInstitutionLine(value),
                          !isTitlePageDateOrLocationNoise(value) {
                    candidates.append(value)
                }
            }
        }
        let orderedCandidates = explicitCandidates + candidates.filter {
            !explicitCandidates.contains($0)
        }
        guard let first = orderedCandidates.first else { return nil }
        return Detection(value: first, confidence: .medium,
                         source: "Detected as a name in the first two-page title block — please check",
                         rule: "title_page_student_name",
                         candidates: Array(orderedCandidates.dropFirst().prefix(4)))
    }

    func titlePagePersonValue(_ raw: String) -> String? {
        titlePagePersonValues(raw).first
    }

    func titlePagePersonValue(in lines: [String], at index: Int) -> String? {
        titlePagePersonValues(in: lines, at: index).first
    }

    func titlePagePersonValues(in lines: [String], at index: Int) -> [String] {
        guard lines.indices.contains(index) else { return [] }
        let line = lines[index]
        var values = titlePagePersonValues(line)
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowerLine = trimmed.lowercased()
        // Repository covers sometimes extract a byline as three lines:
        // "By" / "S" / "tefan Sarkadi". Reassemble those short runs
        // before applying the normal name-shape checks.
        if ["by", "by:", "author:", "author :"].contains(lowerLine), index + 1 < lines.count {
            let next = lines[index + 1].trimmingCharacters(in: .whitespacesAndNewlines)
            if index + 2 < lines.count, next.count <= 2 {
                values += titlePagePersonValues("\(lowerLine) \(next) \(lines[index + 2])")
            } else {
                values += titlePagePersonValues("\(lowerLine) \(next)")
            }
        } else if trimmed.count <= 2, index + 1 < lines.count {
            // A PDF text layer can split an initial from the rest of a first
            // name even when there is no standalone "By" line.
            values += titlePagePersonValues("\(line) \(lines[index + 1])")
        }
        var unique: [String] = []
        for value in values where !unique.contains(value) { unique.append(value) }
        return unique
    }

    func titlePagePersonValues(_ raw: String) -> [String] {
        let line = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = line.lowercased()
        // Some thesis generators place the title and author marker on one
        // extracted line: "Title Author: Name Supervisors: ...".
        for marker in ["author:", "author :"] {
            if let markerRange = lower.range(of: marker) {
                let value = trimPersonTail(String(line[markerRange.upperBound...]))
                let collapsed = collapseSplitInitials(value)
                return looksLikeTitlePagePersonName(collapsed) ? [collapsed] : []
            }
        }
        // Group cover sheets often use: "1. Surname, First name ID: ...".
        if let marker = line.range(of: "id:", options: .caseInsensitive) {
            let before = String(line[..<marker.lowerBound])
            if let dot = before.firstIndex(of: ".") {
                let groupName = before[before.index(after: dot)...]
                    .replacingOccurrences(of: ",", with: " ")
                    .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if isPlausiblePerson(groupName),
                   groupName.split(separator: " ").count <= 4 {
                    return [groupName]
                }
            }
        }
        let prefixes = ["written by:", "written by ", "author:", "author ", "by "]
        for prefix in prefixes where lower.hasPrefix(prefix) {
            let start = line.index(line.startIndex, offsetBy: prefix.count)
            let rawValue = String(line[start...]).trimmingCharacters(in: .whitespacesAndNewlines)
            let value = collapseSplitInitials(trimPersonTail(rawValue))
            return looksLikeTitlePagePersonName(value) ? [value] : []
        }
        let collapsed = collapseSplitInitials(line)
        return looksLikeTitlePagePersonName(collapsed) ? [collapsed] : []
    }

    func collapseSplitInitials(_ s: String) -> String {
        s.replacingOccurrences(of: #"\b([A-Z])\s+([a-z]{2,})\b"#,
                               with: "$1$2", options: .regularExpression)
    }

    func trimPersonTail(_ s: String) -> String {
        let lower = s.lowercased()
        let markers = [" supervisors:", " supervisor:", " advisors:",
                       " advisor:", " lecturers:", " lecturer:",
                       " submitted", " a thesis"]
        for marker in markers where lower.contains(marker) {
            if let range = lower.range(of: marker) {
                return String(s[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func looksLikeTitlePagePersonName(_ s: String) -> Bool {
        guard isPlausiblePerson(s) else { return false }
        let words = s.split(separator: " ")
        guard (2...4).contains(words.count) else { return false }
        let normalized = s.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        // Guidance/manual pages can contain title-cased section labels that
        // satisfy the shape of a person's name. They are not identity data.
        if ["references cited", "references", "cited references", "be descriptive"].contains(normalized) {
            return false
        }

        // These words make a line read like a degree/title/department heading,
        // not like a person's name. The list is deliberately conservative.
        let nonNameWords = ["a", "an", "the", "and", "of", "for", "to", "in", "with",
                            "from", "by", "university", "college", "faculty", "school",
                            "department", "bachelor", "master", "doctor", "thesis",
                            "dissertation", "project", "report", "system", "development",
                            "engineering", "technology", "management", "monitoring",
                            "control", "classification", "optimisation", "optimization",
                            "final", "paper", "essay", "written", "work", "submission",
                            "end", "user", "licence", "license", "agreement", "programming",
                            "assignments", "assignment", "capstone", "program", "general",
                            "guidelines", "guidance", "notes", "cover", "page", "title",
                            "pre-registration", "programme", "handbook", "using", "word", "styles",
                            "candidate", "declaration", "template", "mathematics", "computer", "science",
                            "temporary", "policy", "chapter", "annex", "appendix", "font", "times",
                            "roman", "academic", "manual", "procedures", "presentation", "format",
                            "formatting", "layout", "page", "pages", "specific", "aims", "approach",
                            "results", "methods", "background", "rationale", "options",
                            "personal", "reflection"]
        guard !words.contains(where: {
            $0.count > 1 && nonNameWords.contains($0.lowercased())
        }) else { return false }
        return words.allSatisfy(isNameWordCased)
    }

    func isNameWordCased(_ word: Substring) -> Bool {
        let letters = word.filter(\.isLetter)
        guard !letters.isEmpty else { return false }
        let allUpper = letters.allSatisfy(\.isUppercase)
        let titleCased = word.first?.isUppercase == true &&
            word.dropFirst().allSatisfy { !$0.isLetter || $0.isLowercase }
        return allUpper || titleCased
    }

    // MARK: - Module code / title

    func detectModuleCode(in doc: PDFTextDocument) -> Detection {
        // Letter prefix capped at 8, not 6: some real department codes run longer
        // (e.g. Cardiff Business School's "MANGTBL"), and a 6-letter cap silently
        // dropped those to .missing with no candidate at all, even right after an
        // explicit "Module Code:" label.
        let generic = #"\b[A-Z]{2,8}-?\d{2,4}(?:[A-Z])?(?:-\d+(?:-\d+)?)?"#
        for hit in findLabels(Self.moduleLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
                        if let v = tail.firstMatch(generic), v.count >= 4 {
                return Detection(value: v, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_module_code")
            }
        }
        var seen: [String] = []
        for line in firstLines(doc, count: 30) {
            let lower = line.lowercased()
            if lower.contains("reference") || lower.contains("bibliograph") { continue }
            // The fallback is intentionally LOW confidence: short codes such
            // as CS101 are common, but can also resemble document/version
            // tokens in guidance pages.
            for v in line.allMatches(#"\b[A-Z]{2,8}-?\d{2,4}(?:[A-Z])?(?:-\d+(?:-\d+)?)?\b"#)
            where !seen.contains(v) && !["ISBN", "ISSN"].contains(v.uppercased()) {
                seen.append(v)
            }
        }
        if let v = seen.first {
            return Detection(value: v, confidence: .low,
                             source: "Detected module-code-shaped text on an early page — please check",
                             rule: "pattern_module_code")
        }
        return .missing("No module code found")
    }

    func detectModuleTitle(in doc: PDFTextDocument) -> Detection {
        for hit in findLabels(Self.moduleTitleLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if isPlausibleTitle(tail) {
                return Detection(value: tail, confidence: .high,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_module_title")
            }
        }
        return .missing("No module title found")
    }

    // MARK: - University

    func detectUniversity(in doc: PDFTextDocument) -> Detection {
        let uniRe = #"(?:[Tt]he\s+)?(?:University|UNIVERSITY)\s+(?:of|OF)\s+[A-Z][\w'&.-]*(?:\s+[A-Z][\w'&.-]*)*|(?:Universiti|UNIVERSITI)\s+[A-Z][\w'&.-]*(?:\s+[A-Z][\w'&.-]*)*|[A-Z][\w'&.-]*(?:\s+[A-Z][\w'&.-]*)*\s+(?:University|College|Institute|UNIVERSITY|COLLEGE|INSTITUTE)(?:\s*-\s*[A-Z][\w'&.-]*)?(?:\s+(?:of\s+)?[A-Z][\w'&.-]*){0,3}"#

        // Partnership/bibliography mentions are not the student's institution.
        let nonInstitutionWords = ["partnership", "partner", "association", "merger",
                                   "validated by", "awarded by", "submitted to",
                                   "in fulfilment", "in fulfillment", "requirements for",
                                   "thesis submitted"]
        // Page-1 first line is the strongest institution signal (cover sheets put
        // the primary institution first; partnership/bibliography mentions come later).
        if let firstLine = doc.pages.first?.lines.first,
           !nonInstitutionWords.contains(where: { firstLine.lowercased().contains($0) }),
           let v = bestUniversityMatch(in: firstLine, pattern: uniRe), isUsefulUniversityName(v) {
            return Detection(value: v, confidence: .high,
                             source: "Found institution name as page-1 heading",
                             rule: "pattern_university_first_line")
        }
        for page in doc.pages.prefix(2) {
            for line in page.lines
            where !nonInstitutionWords.contains(where: { line.lowercased().contains($0) }) {
                if let v = bestUniversityMatch(in: line, pattern: uniRe), isUsefulUniversityName(v) {
                    return Detection(value: v, confidence: .high,
                                     source: "Found institution name on page \(page.pageNumber)",
                                     rule: "pattern_university")
                }
            }
        }
        // First prominent page-1 line heuristic (covers short names like “UWE Bristol”).
        if let first = doc.pages.first?.lines.first,
           first.count >= 3, first.count <= 80 {
            let lower = first.lowercased()
            let excludeWords = ["student", "module", "project", "assignment", "declaration",
                                "word count", "date", "faculty", "school", "department",
                                "candidate", "submission", "report", "capstone", "final"]
            if !excludeWords.contains(where: { lower.contains($0) }), looksLikeHeading(first) {
                return Detection(value: first, confidence: .medium,
                                 source: "Detected institution name as page-1 heading — please check",
                                 rule: "heading_university")
            }
        }
        for hit in findLabels(Self.universityLabels, in: doc, maxPage: 2) {
            let tail = remainder(of: hit.line, after: hit.label)
            // Reject fragments like “of Arts, Design and Humanities”.
            guard !tail.isEmpty, let fc = tail.first, fc.isUppercase else { continue }
            if tail.count > 2, tail.count < 80, isUsefulUniversityName(tail) {
                return Detection(value: tail, confidence: .medium,
                                 source: "Found after “\(hit.label)” on page \(hit.page.pageNumber)",
                                 rule: "label_university")
            }
        }
        if let t = doc.metadataTitle, let v = t.firstMatch(uniRe) {
            return Detection(value: v, confidence: .low,
                             source: "Found in PDF metadata (untrusted)",
                             rule: "metadata_university")
        }
        return .missing("No university found")
    }

    func isUsefulUniversityName(_ value: String) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["university", "the university", "college", "the college",
            "graduate college", "the graduate college", "graduate school",
            "the graduate school"].contains(normalized) {
            return false
        }
        // A wrapper such as “Graduate College” is not the awarding institution;
        // let a later University/College line supply the useful value.
        return !normalized.hasPrefix("graduate college ") &&
            !normalized.hasPrefix("graduate school ")
    }

    func bestUniversityMatch(in line: String, pattern: String) -> String? {
        let matches = line.allMatches(pattern)
        guard !matches.isEmpty else { return nil }
        func score(_ value: String) -> Int {
            let lower = value.lowercased()
            var result = value.count
            if lower.contains("university") || lower.contains("universiti") { result += 1000 }
            if lower.contains("institute") { result += 200 }
            return result
        }
        guard let best = matches.max(by: { score($0) < score($1) }) else { return nil }
        let lowerLine = line.lowercased()
        let lowerBest = best.lowercased()
        if lowerBest.hasPrefix("the ") &&
            (lowerLine.contains(" at \(lowerBest)") || lowerLine.contains(" in \(lowerBest)")) {
            return String(best.dropFirst(4))
        }
        guard let first = best.first, first.isLowercase else { return best }
        return String(first).uppercased() + best.dropFirst()
    }

    // MARK: - Project / assignment title

    func detectProjectTitle(in doc: PDFTextDocument) -> Detection {
        var candidates: [String] = []
        for hit in findLabels(Self.projectLabels, in: doc, maxPage: 3) {
            let tail = remainder(of: hit.line, after: hit.label)
            if isPlausibleTitle(tail), !isGenericProjectHeading(tail),
               !isTitlePageNoise(tail), !candidates.contains(tail) {
                candidates.append(tail)
            }
        }
        if let explicit = candidates.first {
            let conf: Confidence = candidates.count == 1 ? .high : .medium
            return Detection(value: explicit, confidence: conf,
                             source: "Found an explicit title label",
                             rule: "label_project_title",
            candidates: Array(candidates.dropFirst()))
        }

        if let titlePage = detectTitlePageProjectTitle(in: doc) {
            return titlePage
        }

        // Prominent heading fallback over the first two pages.
        let exclude = ["university", "module", "student", "submission", "declaration",
                       "word count", "date", "references", "contents", "abstract",
                       "candidate", "registration", "font:", "margins:", "line spacing:",
                       "page layout", "title page", "title-page"]
        var headingCandidates: [String] = []
        for page in doc.pages.prefix(2) {
            for line in page.lines {
                guard line.count >= 8, line.count <= 120 else { continue }
                let lower = line.lowercased()
                if exclude.contains(where: { lower.contains($0) }) { continue }
                if !line.hasSuffix("."), looksLikeHeading(line) {
                    let cleaned = trimTitlePageMarkers(line)
                    if isPlausibleTitle(cleaned), !isTitlePageNoise(cleaned),
                       !isTitlePageInstitutionLine(cleaned),
                       !looksLikeTitlePagePersonName(cleaned) {
                        headingCandidates.append(cleaned)
                    }
                }
            }
        }
        var counts: [String: Int] = [:]
        for c in headingCandidates { counts[c, default: 0] += 1 }
        // Candidate ranking: explicit repetition dominates, then length
        // (longer = more title-like), with a hard penalty for generic academic
        // headings that are almost never the student's project title.
        let genericWords = ["assignment", "report", "coursework", "assessment",
                            "submission", "cover sheet", "contents", "introduction",
                            "abstract", "dissertation", "portfolio", "essay",
                            "project report", "final report", "appendix", "approach",
                            "personal reflection", "specific aims", "methods", "results",
                            "background", "rationale", "options"]
        func score(_ s: String) -> Int {
            var v = counts[s]! * 1000 + s.count
            let lower = s.lowercased()
            if genericWords.contains(where: { lower.hasPrefix($0) || lower == $0 }) {
                v -= 5000
            } else if genericWords.contains(where: { lower.contains($0) }) {
                v -= 500
            }
            return v
        }
        let ranked = headingCandidates.sorted { score($0) > score($1) }
        var unique: [String] = []
        for r in ranked where !unique.contains(r) { unique.append(r) }
        if let best = unique.first {
            return Detection(value: best, confidence: .medium,
                             source: "Detected as a title heading — please check",
                             rule: "heading_project_title",
                             candidates: Array(unique.dropFirst().prefix(4)))
        }

        if let t = doc.metadataTitle, isPlausibleTitle(t) {
            return Detection(value: t, confidence: .low,
                             source: "Found in PDF metadata (untrusted)",
                             rule: "metadata_title")
        }
        return .missing("No project title found")
    }

    func isGenericProjectHeading(_ value: String) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["approach", "specific aims", "results", "methods", "background",
                "background and rationale", "rationale", "options", "personal reflection",
                "introduction", "abstract"].contains(normalized)
    }

    /// Looks for a title-page heading before using the broader heading scan.
    /// This handles cover sheets where the title is visually prominent but
    /// extracted text contains no "Project title:" label.
    func detectTitlePageProjectTitle(in doc: PDFTextDocument) -> Detection? {
        guard !doc.pages.isEmpty else { return nil }
        let lines = Array(doc.pages.prefix(2).flatMap(\.lines).prefix(80))
        let pageText = lines.joined(separator: " ").lowercased()
        let hasSubmissionContext = ["thesis", "dissertation", "degree", "bachelor", "master",
                                    "doctor", "submitted", "candidate", "supervisor",
                                    "awarding institution", "electronic thesis",
                                    "copyright of this thesis"]
            .contains(where: { pageText.contains($0) })
        let hasUnlabelledName = lines.indices.contains {
            titlePagePersonValue(in: lines, at: $0) != nil
        }
        let hasExplicitTitle = lines.contains {
            let lower = $0.lowercased()
            return lower.hasPrefix("title:") || lower.hasPrefix("project title:") ||
                lower.hasPrefix("assignment title:") || lower.hasPrefix("assessment title:")
        }
        // A university heading alone is not enough: ordinary cover sheets and
        // synthetic coursework pages frequently contain other headings.
        guard hasSubmissionContext || hasUnlabelledName || hasExplicitTitle else { return nil }

        var ranked: [(value: String, score: Int)] = []
        for (index, rawLine) in lines.enumerated() {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let value = titlePageTitleValue(line), isPlausibleTitle(value) else { continue }
            // A generated title page may put the title and "Author: ..." on
            // the same extracted line. The title parser has already removed
            // that marker, so retain the cleaned title in that case.
            guard titlePagePersonValue(in: lines, at: index) == nil || value != line,
                  !isTitlePageNoise(value), !isTitlePageStaffLine(value) else { continue }
            guard !isTitlePageInstitutionLine(value) else { continue }
            guard !["by", "by:", "author:", "author :"].contains(line.lowercased()) else { continue }

            var score = value.count
            if line.lowercased().hasPrefix("title:") ||
                line.lowercased().hasPrefix("project title:") ||
                line.lowercased().hasPrefix("assignment title:") {
                score += 300
            }
            if value == value.uppercased() { score += 40 }
            score += max(0, 30 - index)
            ranked.append((value, score))
        }

        // Repository wrappers place a short work title before a licence page.
        // Prefer the first clean heading before that wrapper rather than a
        // long sentence from the licence terms.
        if pageText.contains("electronic thesis"),
           let licenceIndex = lines.firstIndex(where: {
               $0.lowercased().contains("end user licence") ||
               $0.lowercased().contains("end user license")
           }) {
            for rawLine in lines[..<licenceIndex] {
                let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let value = titlePageTitleValue(line), isPlausibleTitle(value),
                      !isTitlePageNoise(value), !isTitlePageInstitutionLine(value),
                      !value.contains("/") else { continue }
                ranked.append((value, 1800))
                break
            }
        }

        // Many thesis covers split one title over several uppercase lines.
        // Recombine the heading block immediately above the first author line.
        let authorMarkerIndex = lines.indices.first(where: { index in
            let lower = lines[index].trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return lower == "by" || lower == "by:" || lower.hasPrefix("author:") ||
                lower.hasPrefix("author :") || lower.hasPrefix("written by:")
        })
        if let nameIndex = authorMarkerIndex ?? lines.indices.first(where: {
            titlePagePersonValue(in: lines, at: $0) != nil
        }) {
            // University title pages often place a degree statement and
            // divider lines between the heading and the `by` marker. Keep a
            // wider bounded window so split titles such as Missouri's
            // two-line heading can still be recombined.
            let start = max(0, nameIndex - 20)
            let parts = lines[start..<nameIndex].enumerated().compactMap { offset, raw -> String? in
                let absoluteIndex = start + offset
                let line = raw.trimmingCharacters(in: .whitespacesAndNewlines)
                let value = titlePageTitleValue(line) ?? {
                    guard let first = line.first(where: { $0.isLetter }),
                          first.isLowercase, line.count >= 8, line.count <= 120,
                          !line.hasSuffix(".") else { return nil }
                    return line
                }()
                guard let value,
                      (authorMarkerIndex != nil || titlePagePersonValue(in: lines, at: absoluteIndex) == nil),
                      !["by", "by:", "author:", "author :"].contains(line.lowercased()),
                      !isTitlePageNoise(value), !isTitlePageStaffLine(value),
                      !isTitlePageInstitutionLine(value) else { return nil }
                return value
            }
            var uniqueParts: [String] = []
            for part in parts where !uniqueParts.contains(part) { uniqueParts.append(part) }
            let joined = uniqueParts.joined(separator: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if isPlausibleTitle(joined), !looksLikeTitlePagePersonName(joined) {
                ranked.append((joined, 500 + joined.count))
            }
        }

        guard !ranked.isEmpty else { return nil }
        let ordered = ranked.sorted { $0.score > $1.score }
        var unique: [String] = []
        for candidate in ordered.map(\.value) where !unique.contains(candidate) {
            unique.append(candidate)
        }
        guard let best = unique.first else { return nil }
        let cleanedBest = trimTitlePageMarkers(best)
        guard isPlausibleTitle(cleanedBest), !isTitlePageNoise(cleanedBest) else { return nil }
        return Detection(value: cleanedBest, confidence: .medium,
                         source: "Detected as a heading in the page-1 title block — please check",
                         rule: "title_page_heading",
                         candidates: Array(unique.dropFirst().prefix(4)))
    }

    func titlePageTitleValue(_ line: String) -> String? {
        let lower = line.lowercased()
        let prefixes = ["project title:", "assignment title:", "assessment title:", "title:"]
        for prefix in prefixes where lower.hasPrefix(prefix) {
            let start = line.index(line.startIndex, offsetBy: prefix.count)
            return trimTitlePageMarkers(String(line[start...]))
        }
        guard !line.hasSuffix("."), looksLikeHeading(line) else { return nil }
        return trimTitlePageMarkers(line)
    }

    func trimTitlePageMarkers(_ raw: String) -> String {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let initialLower = value.lowercased()
        // Repository and institutional title pages sometimes prefix the real
        // title with a document-type banner. Keep the title, not the banner,
        // as the filename component.
        for prefix in ["doctoral thesis ", "doctoral dissertation "] where initialLower.hasPrefix(prefix) {
            value = String(value.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            break
        }
        let lower = value.lowercased()
        let markers = [" by:", " author:", " author :", " supervisors:",
                       " supervisor:", " advisors:", " advisor:"]
        for marker in markers where lower.contains(marker) {
            if let range = lower.range(of: marker) {
                return String(value[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return value
    }

    func isTitlePageNoise(_ s: String) -> Bool {
        let lower = s.lowercased()
        if isTitlePageDateOrLocationNoise(s) { return true }
        if isTitlePageStaffLine(s) { return true }
        if ["thesis", "dissertation", "a thesis", "a dissertation"].contains(lower) {
            return true
        }
        if lower.range(of: #"^\s*\d+[.)]\s"#, options: .regularExpression) != nil { return true }
        let noise = ["declaration", "i certify", "partial fulfilment", "partial fulfillment",
                     "requirements for the degree", "submitted", "presented to",
                     "final paper", "undergraduate", "capstone project",
                     "under the supervision", "supervision", "assistant professor",
                     "branding and identity", "downloaded from", "research portal", "end user licence", "end user license",
                     "abstract", "bibliography", "list of figures", "list of tables",
                     "table of contents",
                     "supervisor:", "by:", "author:",
                     "advisor:", "lecturer:", "module leader:", "copyright", "references",
                     "contents", "template", "checklist", "guidance", "guidelines", "acknowledg",
                     "formatting", "word count", "master of", "bachelor of", "doctor of",
                     "degree of", "faculty of", "department of", "school of", "university of",
                     "temporary policy", "chapter", "annex", "appendix", "font:",
                     "any legible font", "times new roman", "page layout", "line spacing",
                     "presentation of theses", "academic year", "specific aims", "approach",
                     "results", "methods", "rationale", "options",
                     "electronic thesis", "electronic dissertation", "brand and logo",
                     "worldwide image", "type faces", "color palate", "policies towards the use",
                     "developed to help you", "integral parts of our", "brand’s integrity",
                     "brand's integrity", "applied project", "b.sc. computer science",
                     "sample title page", "example of title page", "all margins",
                     "be descriptive",
                     "do not use bold", "double-spaced", "capital letters", "section is",
                     "student name", "student's name", "student’s name", "appropriate degree", "updated:",
                     "module no", "module code", "student no", "student number", "name:",
                     "spaced if more than one line", "committee", "no titles are permitted",
                     "co-advisor line", "graduating", "this is the term", "type your committee",
                     "member names", "do not print a number", "ph.d.", "except for those noted",
                     "instructions for"]
        return noise.contains(where: { lower.contains($0) })
    }

    /// Committee/adviser lines are common immediately after a title-page
    /// byline. They can look like title-case headings, but must never become a
    /// project title merely because the real title was filtered for academic
    /// wording such as “dissertation”.
    func isTitlePageStaffLine(_ s: String) -> Bool {
        let lower = s.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let markers = ["professor ", "prof. ", "dr. ", "dr ", "advisor:",
                       "adviser:", "supervisor:", "director of research",
                       "committee chair", "doctoral committee", "chair:"]
        return markers.contains(where: { lower.contains($0) })
    }

    func isTitlePageDateOrLocationNoise(_ s: String) -> Bool {
        let lower = s.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let months = ["january", "february", "march", "april", "may", "june",
                      "july", "august", "september", "october", "november", "december"]
        let seasons = ["spring", "summer", "fall", "autumn", "winter"]
        if (months + seasons).contains(where: { lower.contains($0) }) &&
            lower.range(of: #"\b\d{4}\b"#, options: .regularExpression) != nil {
            return true
        }
        let states = ["alabama", "alaska", "arizona", "arkansas", "california", "colorado",
                      "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
                      "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
                      "maine", "maryland", "massachusetts", "michigan", "minnesota",
                      "mississippi", "missouri", "montana", "nebraska", "nevada",
                      "new hampshire", "new jersey", "new mexico", "new york",
                      "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
                      "pennsylvania", "rhode island", "south carolina", "south dakota",
                      "tennessee", "texas", "utah", "vermont", "virginia", "washington",
                      "west virginia", "wisconsin", "wyoming"]
        if let comma = lower.lastIndex(of: ",") {
            let suffix = lower[lower.index(after: comma)...]
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if states.contains(String(suffix)) { return true }
        }
        return false
    }

    func isTitlePageInstitutionLine(_ s: String) -> Bool {
        let lower = s.lowercased()
        let institutionWords = ["university", "universiti", "college", "faculty", "school",
                                "department", "institute", "campus"]
        return institutionWords.contains(where: { lower.contains($0) })
    }

    func looksLikeHeading(_ s: String) -> Bool {
        let letters = s.filter(\.isLetter).count
        guard let firstLetter = s.first(where: { $0.isLetter }) else { return false }
        // Sentence fragments from procedural guidance frequently pass the
        // length test. A real cover/title heading is normally title-cased or
        // uppercase; lowercase prose remains review-only rather than becoming
        // an automatic filename component.
        guard firstLetter.isUppercase || s == s.uppercased() else { return false }
        return Double(letters) / Double(max(s.count, 1)) > 0.6
            && !s.contains("|") && !s.hasSuffix(".pdf")
    }

    func isPlausibleTitle(_ s: String) -> Bool {
        s.count >= 3 && s.count <= 240 &&
        !s.lowercased().hasPrefix("http") &&
        !s.contains("@") && !s.contains("/")
    }
}


// MARK: - Labelled-value machinery

extension FieldDetector {
    typealias LabelHit = (label: String, line: String, page: PDFTextDocument.Page)

    func findLabels(_ labels: [String], in doc: PDFTextDocument, maxPage: Int) -> [LabelHit] {
        var hits: [LabelHit] = []
        let ordered = labels.sorted { $0.count > $1.count } // most specific first
        for page in doc.pages.prefix(maxPage) {
            for line in page.lines {
                let lower = line.lowercased()
                for label in ordered {
                    if lower.hasPrefix(label) || lower.contains("\(label):") || lower.contains("\(label) :") {
                        hits.append((label.capitalized, line, page))
                        break
                    }
                }
            }
        }
        return hits
    }

    /// Text after a label within the same line, with separator stripped.
    func remainder(of line: String, after label: String) -> String {
        guard let r = line.lowercased().range(of: label.lowercased()) else { return "" }
        var rest = String(line[r.upperBound...])
        rest = regexReplace(rest, pattern: #"^\s*[:：\-–—]?\s*"#) { _ in "" }
        return rest.trimmingCharacters(in: .whitespaces)
    }

    func firstLines(_ doc: PDFTextDocument, count: Int) -> [String] {
        Array(doc.pages.prefix(2).flatMap(\.lines).prefix(count))
    }
}

// MARK: - Regex helpers

extension String {
    func firstMatch(_ pattern: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
        let ns = NSRange(startIndex..., in: self)
        guard let m = re.firstMatch(in: self, range: ns), m.range.location != NSNotFound,
              let r = Range(m.range, in: self) else { return nil }
        return String(self[r])
    }

    func allMatches(_ pattern: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let ns = NSRange(startIndex..., in: self)
        return re.matches(in: self, range: ns).compactMap { m in
            Range(m.range, in: self).map { String(self[$0]) }
        }
    }
}
