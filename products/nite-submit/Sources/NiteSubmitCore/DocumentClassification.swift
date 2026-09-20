import Foundation

/// Broad document-purpose classification used only to improve review context.
/// It never authorises or blocks a file operation by itself.
public enum DocumentKind: String, Codable, Equatable, Sendable {
    case likelySubmission = "likely_submission"
    case guidanceTemplate = "guidance_template"
}

public struct DocumentClassification: Codable, Equatable, Sendable {
    public var kind: DocumentKind
    public var reason: String?

    public init(kind: DocumentKind = .likelySubmission, reason: String? = nil) {
        self.kind = kind
        self.reason = reason
    }
}

/// The document-content identity rule is deliberately separate from the
/// filename template. Departments may require a named cover sheet, prohibit
/// names for anonymous marking, or give no universal rule at all.
public enum DocumentIdentityPolicy: String, Codable, CaseIterable, Sendable {
    case noRule = "no_rule"
    case nameRequired = "name_required"
    case nameProhibited = "name_prohibited"
}

public enum DocumentIdentityStatus: String, Codable, Equatable, Sendable {
    case notChecked = "not_checked"
    case satisfied
    case nameMissing = "name_missing"
    case namePresent = "name_present"
    case unavailable
}

public struct DocumentIdentityCheck: Codable, Equatable, Sendable {
    public var policy: DocumentIdentityPolicy
    public var status: DocumentIdentityStatus
    public var evidence: String

    public init(policy: DocumentIdentityPolicy = .noRule,
                status: DocumentIdentityStatus = .notChecked,
                evidence: String = "No document identity rule selected") {
        self.policy = policy
        self.status = status
        self.evidence = evidence
    }

    public var isBlocking: Bool {
        switch status {
        case .nameMissing, .namePresent, .unavailable: return policy != .noRule
        case .notChecked, .satisfied: return false
        }
    }

    public var blockingReason: String? {
        guard isBlocking else { return nil }
        return evidence
    }
}

public extension FieldDetector {
    /// Name-required checks the first two extracted pages, where a cover
    /// sheet/title page normally lives. Anonymous checks those opening pages
    /// plus explicit identity labels anywhere else in the extracted text: a
    /// later labelled “Student Name” or “Author” must not silently pass an
    /// anonymous submission. An unlabelled person-shaped name in body text is
    /// deliberately not enough to block because it may be a cited author.
    func checkDocumentIdentity(in doc: PDFTextDocument,
                               policy: DocumentIdentityPolicy) -> DocumentIdentityCheck {
        guard policy != .noRule else {
            return DocumentIdentityCheck(policy: policy, status: .notChecked,
                                         evidence: "No document identity rule selected")
        }
        guard doc.hasUsableText else {
            return DocumentIdentityCheck(policy: policy, status: .unavailable,
                                         evidence: "Could not verify the first two pages because this PDF has no usable text")
        }

        let firstPages = Array(doc.pages.prefix(2))
        let firstPageDocument = PDFTextDocument(
            pageCount: firstPages.count,
            pages: firstPages,
            metadataTitle: doc.metadataTitle,
            metadataAuthor: doc.metadataAuthor,
            textOrigin: doc.textOrigin)
        let openingName = detectStudentName(in: firstPageDocument)
        let laterExplicitName = policy == .nameProhibited
            ? detectExplicitStudentNameAnywhere(in: doc)
            : nil
        let present = !openingName.isMissing || laterExplicitName != nil
        switch policy {
        case .nameRequired:
            return present
                ? DocumentIdentityCheck(policy: policy, status: .satisfied,
                                        evidence: "Student name found in the first two pages")
                : DocumentIdentityCheck(policy: policy, status: .nameMissing,
                                        evidence: "Student name is required but was not found in the first two pages")
        case .nameProhibited:
            if !openingName.isMissing {
                return DocumentIdentityCheck(policy: policy, status: .namePresent,
                                             evidence: "Student name found in the first two pages; anonymous work must not contain a name")
            }
            if let laterExplicitName {
                return DocumentIdentityCheck(policy: policy, status: .namePresent,
                                             evidence: "\(laterExplicitName.source ?? "An explicit student identity label was found") on a later page; anonymous work must not contain a name")
            }
            return DocumentIdentityCheck(policy: policy, status: .satisfied,
                                         evidence: "No labelled student name found in the extracted document text")
        case .noRule:
            return DocumentIdentityCheck(policy: policy, status: .notChecked,
                                        evidence: "No document identity rule selected")
        }
    }

    /// Find identity values explicitly labelled outside the opening pages.
    /// This is intentionally narrower than normal student-name extraction:
    /// references and body prose can contain person names, while a labelled
    /// “Student Name”, “Submitted by”, “Author”, or “Candidate” field is an
    /// actionable anonymity conflict that should be held for review.
    func detectExplicitStudentNameAnywhere(in doc: PDFTextDocument) -> Detection? {
        let labels = ["student name", "name of student", "candidate name",
                      "submitted by", "author", "candidate"]
        for hit in findLabels(labels, in: doc, maxPage: doc.pages.count) {
            let tail = remainder(of: hit.line, after: hit.label)
            if isPlausiblePerson(tail) {
                return Detection(value: tail, confidence: .medium,
                                 source: "Explicit identity label found on page \(hit.page.pageNumber)",
                                 rule: "identity_label_anywhere")
            }
        }

        let orderedLabels = labels.sorted { $0.count > $1.count }
        for page in doc.pages.dropFirst(2) {
            for index in page.lines.indices {
                let line = page.lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
                let lower = line.lowercased()
                guard orderedLabels.contains(where: {
                    lower == $0 || lower == "\($0):" || lower == "\($0) :"
                }), index + 1 < page.lines.count else { continue }
                let value = page.lines[index + 1].trimmingCharacters(in: .whitespacesAndNewlines)
                guard isPlausiblePerson(value) else { continue }
                return Detection(value: value, confidence: .medium,
                                 source: "Explicit identity label found on page \(page.pageNumber)",
                                 rule: "identity_label_anywhere")
            }
        }
        return nil
    }

    /// Detect strong first-page guidance/template signals. This is deliberately
    /// conservative: ordinary assignment prompts may contain instructions,
    /// so a single generic word such as “submission” is not enough.
    func classifyDocument(in doc: PDFTextDocument) -> DocumentClassification {
        let lines = Array(doc.pages.prefix(2).flatMap(\.lines).prefix(80))
        let text = lines.joined(separator: " ")
            .lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)

        let signals = [
            "formatting guidelines", "format guidelines", "submission guidelines",
            "submission guidance", "thesis guidelines", "dissertation guidelines",
            "style guide", "sample title page", "example of title page",
            "cover page should include", "submission checklist", "assignment header",
            "recommended format", "format of your", "instructions for",
            "this guide", "template", "example of thesis title page",
            "date of submission for examination", "date of resubmission for examination",
            "please use a separate cover sheet", "research project must be based on",
            "the report should be written", "style is equally as important as content",
            "capstone manual", "be descriptive"
        ]
        guard let signal = signals.first(where: { text.contains($0) }) else {
            return DocumentClassification()
        }
        return DocumentClassification(
            kind: .guidanceTemplate,
            reason: "First-page guidance/template wording detected: “\(signal)”"
        )
    }
}
