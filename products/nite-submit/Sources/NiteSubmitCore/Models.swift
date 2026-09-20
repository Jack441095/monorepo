import Foundation

/// Confidence states for detected fields.
public enum Confidence: String, Codable, Comparable, Sendable {
    case high
    case medium
    case low
    case missing

    public static func < (lhs: Confidence, rhs: Confidence) -> Bool {
        let rank: [Confidence: Int] = [.missing: 0, .low: 1, .medium: 2, .high: 3]
        return rank[lhs]! < rank[rhs]!
    }
}

/// One detected (or missing) field with full provenance.
public struct Detection: Codable, Equatable, Sendable {
    public var value: String?
    public var confidence: Confidence
    /// Human-readable provenance, e.g. "Found after 'Student Number:' on page 1".
    public var source: String?
    /// Machine-readable rule identifier that produced the value.
    public var rule: String?
    /// Alternative plausible values when confidence is not HIGH.
    public var candidates: [String]

    public init(value: String?, confidence: Confidence,
                source: String? = nil, rule: String? = nil,
                candidates: [String] = []) {
        self.value = value
        self.confidence = confidence
        self.source = source
        self.rule = rule
        self.candidates = candidates
    }

    public static func missing(_ reason: String? = nil) -> Detection {
        Detection(value: nil, confidence: .missing,
                  source: reason ?? "No confident value found")
    }

    public var isMissing: Bool { value == nil || value?.isEmpty == true }
}

/// All extracted submission fields for one document.
public struct SubmissionMetadata: Codable, Equatable, Sendable {
    public var studentName: Detection
    public var studentId: Detection
    public var candidateNumber: Detection
    public var assignmentCode: Detection
    public var groupId: Detection
    public var university: Detection
    public var moduleCode: Detection
    public var moduleTitle: Detection
    public var projectTitle: Detection

    public init(studentName: Detection = .missing(),
                studentId: Detection = .missing(),
                candidateNumber: Detection = .missing(),
                assignmentCode: Detection = .missing(),
                groupId: Detection = .missing(),
                university: Detection = .missing(),
                moduleCode: Detection = .missing(),
                moduleTitle: Detection = .missing(),
                projectTitle: Detection = .missing()) {
        self.studentName = studentName
        self.studentId = studentId
        self.candidateNumber = candidateNumber
        self.assignmentCode = assignmentCode
        self.groupId = groupId
        self.university = university
        self.moduleCode = moduleCode
        self.moduleTitle = moduleTitle
        self.projectTitle = projectTitle
    }

    private enum CodingKeys: String, CodingKey {
        case studentName, studentId, candidateNumber, assignmentCode, groupId,
             university, moduleCode, moduleTitle, projectTitle
    }

    /// Decode older metadata reports that predate the group identifier field.
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        studentName = try c.decodeIfPresent(Detection.self, forKey: .studentName) ?? .missing()
        studentId = try c.decodeIfPresent(Detection.self, forKey: .studentId) ?? .missing()
        candidateNumber = try c.decodeIfPresent(Detection.self, forKey: .candidateNumber) ?? .missing()
        assignmentCode = try c.decodeIfPresent(Detection.self, forKey: .assignmentCode) ?? .missing()
        groupId = try c.decodeIfPresent(Detection.self, forKey: .groupId) ?? .missing()
        university = try c.decodeIfPresent(Detection.self, forKey: .university) ?? .missing()
        moduleCode = try c.decodeIfPresent(Detection.self, forKey: .moduleCode) ?? .missing()
        moduleTitle = try c.decodeIfPresent(Detection.self, forKey: .moduleTitle) ?? .missing()
        projectTitle = try c.decodeIfPresent(Detection.self, forKey: .projectTitle) ?? .missing()
    }

    /// Dictionary view used by the template engine.
    public func variableMap() -> [String: String] {
        var m: [String: String] = [:]
        if let v = studentName.value, !v.isEmpty {
            m["full_name"] = v
            let parts = v.split(separator: " ").map(String.init)
            if v.contains(",") {
                // University title pages commonly print names as
                // “Surname, Given names”. Keep the canonical full name as
                // detected, but expose stable filename components in the
                // conventional given-name/surname order.
                let commaParts = v.split(separator: ",", maxSplits: 1)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                let surname = commaParts.first ?? ""
                let given = commaParts.count > 1
                    ? commaParts[1].split(separator: " ").map(String.init)
                    : []
                if let first = given.first, !first.isEmpty { m["first_name"] = first }
                if !surname.isEmpty, !given.isEmpty { m["last_name"] = surname }
            } else {
                if let first = parts.first { m["first_name"] = first }
                if parts.count > 1 { m["last_name"] = parts.last! }
            }
        }
        if let v = studentId.value { m["student_id"] = v }
        if let v = candidateNumber.value { m["candidate_number"] = v }
        if let v = assignmentCode.value { m["assignment_code"] = v }
        if let v = groupId.value { m["group_id"] = v }
        if let v = university.value { m["university"] = v }
        if let v = moduleCode.value { m["module_code"] = v }
        if let v = moduleTitle.value { m["module_title"] = v }
        if let v = projectTitle.value {
            m["project_title"] = v
            m["assignment_title"] = v
        }
        return m
    }

    public func detection(for field: MetadataField) -> Detection {
        switch field {
        case .studentName: return studentName
        case .studentId: return studentId
        case .candidateNumber: return candidateNumber
        case .assignmentCode: return assignmentCode
        case .groupId: return groupId
        case .university: return university
        case .moduleCode: return moduleCode
        case .moduleTitle: return moduleTitle
        case .projectTitle: return projectTitle
        }
    }

    public mutating func setDetection(_ d: Detection, for field: MetadataField) {
        switch field {
        case .studentName: studentName = d
        case .studentId: studentId = d
        case .candidateNumber: candidateNumber = d
        case .assignmentCode: assignmentCode = d
        case .groupId: groupId = d
        case .university: university = d
        case .moduleCode: moduleCode = d
        case .moduleTitle: moduleTitle = d
        case .projectTitle: projectTitle = d
        }
    }
}

public enum MetadataField: String, CaseIterable, Codable, Sendable {
    case studentName = "student_name"
    case studentId = "student_id"
    case candidateNumber = "candidate_number"
    case assignmentCode = "assignment_code"
    case groupId = "group_id"
    case university = "university"
    case moduleCode = "module_code"
    case moduleTitle = "module_title"
    case projectTitle = "project_title"

    public var displayName: String {
        switch self {
        case .studentName: return "Student name"
        case .studentId: return "Student number"
        case .candidateNumber: return "Candidate number"
        case .assignmentCode: return "Assignment code"
        case .groupId: return "Group ID"
        case .university: return "University"
        case .moduleCode: return "Module code"
        case .moduleTitle: return "Module title"
        case .projectTitle: return "Project title"
        }
    }
}

/// Structured text of a PDF document, produced by the extractor.
/// The field detector operates on this structure only — it never touches raw bytes.
public struct PDFTextDocument: Sendable {
    public enum TextOrigin: String, Sendable {
        case embeddedText = "embedded_text"
        case ocr
    }

    public struct Page: Sendable {
        public var pageNumber: Int
        /// Lines in reading order, whitespace-normalised.
        public var lines: [String]
        public init(pageNumber: Int, lines: [String]) {
            self.pageNumber = pageNumber
            self.lines = lines
        }
    }

    public var pageCount: Int
    public var pages: [Page]
    /// Raw PDF metadata — treated as untrusted hints, never authoritative.
    public var metadataTitle: String?
    public var metadataAuthor: String?
    public var textOrigin: TextOrigin
    public var hasUsableText: Bool

    public init(pageCount: Int, pages: [Page],
                metadataTitle: String? = nil, metadataAuthor: String? = nil,
                textOrigin: TextOrigin = .embeddedText) {
        self.pageCount = pageCount
        self.pages = pages
        self.metadataTitle = metadataTitle
        self.metadataAuthor = metadataAuthor
        self.textOrigin = textOrigin
        self.hasUsableText = pages.contains { !$0.lines.isEmpty }
    }
}
