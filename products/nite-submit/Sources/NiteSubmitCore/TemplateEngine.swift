import Foundation

/// Deterministic naming-template engine.
/// Variables: {first_name} {last_name} {full_name} {student_id} {candidate_number} {university}
/// {module_code} {module_title} {assignment_code} {project_title} {assignment_title}
/// {date} {original_name}
public struct TemplateEngine: Sendable {
    public static let knownVariables = [
        "first_name", "last_name", "full_name", "student_id", "university",
        "candidate_number", "group_id",
        "module_code", "module_title", "project_title", "assignment_title",
        "assignment_code",
        "date", "original_name"
    ]

    public static let defaultDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_GB")
        return f
    }()

    public init() {}

    /// Validate a user-supplied template. Returns human-readable problems.
    public static func validate(_ template: String) -> [String] {
        var problems: [String] = []
        if template.trimmingCharacters(in: .whitespaces).isEmpty {
            problems.append("Template cannot be empty.")
        }
        let openBraces = template.reduce(into: 0) { count, character in
            if character == "{" { count += 1 }
        }
        let closeBraces = template.reduce(into: 0) { count, character in
            if character == "}" { count += 1 }
        }
        if openBraces != closeBraces {
            problems.append("Template has unmatched braces.")
        }
        if let placeholderRegex = try? NSRegularExpression(pattern: #"\{([^{}]*)\}"#) {
            let ns = template as NSString
            let range = NSRange(location: 0, length: ns.length)
            for match in placeholderRegex.matches(in: template, range: range) {
                let token = ns.substring(with: match.range(at: 1))
                if token.isEmpty || token.range(of: #"^\w+$"#, options: .regularExpression) == nil {
                    problems.append("Invalid field placeholder {\(token)}.")
                }
            }
        }
        for v in template.variables() where !knownVariables.contains(v) {
            problems.append("Unknown field {\(v)}.")
        }
        var uniqueProblems: [String] = []
        for problem in problems where !uniqueProblems.contains(problem) {
            uniqueProblems.append(problem)
        }
        return uniqueProblems
    }

    /// Fields the template requires but that have no value.
    /// Blocks the rename instead of silently producing a bad filename.
    public static func missingRequiredFields(_ template: String, values: [String: String]) -> [String] {
        var missing: [String] = []
        // Every metadata-backed field in a template is required. The previous
        // implementation checked only the most common ID/name/title fields,
        // which allowed a module-code or university template to render with a
        // blank component. Date and original_name are generated at render time
        // and therefore do not belong in this list.
        let requirements: [(variable: String, valueKey: String, label: String)] = [
            ("student_id", "student_id", "Student number"),
            ("candidate_number", "candidate_number", "Candidate number"),
            ("group_id", "group_id", "Group ID"),
            ("assignment_code", "assignment_code", "Assignment code"),
            ("first_name", "first_name", "First name"),
            ("last_name", "last_name", "Last name"),
            ("full_name", "full_name", "Student name"),
            ("university", "university", "University"),
            ("module_code", "module_code", "Module code"),
            ("module_title", "module_title", "Module title"),
            ("project_title", "project_title", "Project title"),
            ("assignment_title", "project_title", "Assignment title")
        ]
        var checkedValueKeys: Set<String> = []
        for requirement in requirements where template.contains("{\(requirement.variable)}") {
            // project_title and assignment_title are aliases. Report one
            // clear gap even if both aliases appear in a custom template.
            guard checkedValueKeys.insert(requirement.valueKey).inserted else { continue }
            if values[requirement.valueKey]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true {
                missing.append("\(requirement.label) is required for this naming rule.")
            }
        }
        return missing
    }

    /// Returns fields that have alternatives and therefore need an explicit
    /// choice before a name-bearing filename can be approved. Manual values
    /// are already explicit and are not blocked.
    public static func ambiguousRequiredFields(_ template: String,
                                               metadata: SubmissionMetadata) -> [String] {
        let variables = Set(template.variables())
        var fields: [String] = []
        let nameVariables = Set(["first_name", "last_name", "full_name"])
        if !nameVariables.isDisjoint(with: variables),
           !metadata.studentName.candidates.isEmpty,
           metadata.studentName.rule != "manual" {
            fields.append("Student name")
        }
        return fields
    }

    /// Render the template. Returns `nil` when a required field is missing so
    /// the caller can block the operation rather than guess.
    public static func render(template: String,
                              values: [String: String],
                              originalName: String,
                              date: Date = Date()) -> String? {
        guard validate(template).isEmpty else { return nil }
        let missing = missingRequiredFields(template, values: values)
        guard missing.isEmpty else { return nil }

        var map = values
        map["original_name"] = originalName
        map["date"] = defaultDateFormatter.string(from: date)

        var output = regexReplace(template, pattern: #"\{(\w+)\}"#) { groups in
            guard let key = groups.first else { return "" }
            return map[key] ?? ""
        }
        // Whitespace becomes underscore so compound fields stay joined,
        // then repeated separators collapse.
        output = regexReplace(output, pattern: #"[\s]+"#) { _ in "_" }
        output = regexReplace(output, pattern: #"[\s_\-]{2,}"#) { _ in "_" }
        output = regexReplace(output, pattern: #"^[\s_\-\.]+|[\s_\-\.]+$"#) { _ in "" }

        let cleaned = FilenameSanitizer.sanitize(output)
        return cleaned.isEmpty ? nil : cleaned
    }
}

/// Shared regex-replace helper.
func regexReplace(_ s: String, pattern: String,
                  transform: ([String]) -> String) -> String {
    guard let re = try? NSRegularExpression(pattern: pattern) else { return s }
    let ns = s as NSString
    let matches = re.matches(in: s, range: NSRange(location: 0, length: ns.length))
    var out = ""
    var cursor = 0
    for m in matches {
        out += ns.substring(with: NSRange(location: cursor, length: m.range.location - cursor))
        var groups: [String] = []
        for i in 1..<m.numberOfRanges {
            let r = m.range(at: i)
            groups.append(r.location != NSNotFound ? ns.substring(with: r) : "")
        }
        out += transform(groups)
        cursor = m.range.location + m.range.length
    }
    out += ns.substring(from: cursor)
    return out
}

extension String {
    public func variables() -> [String] {
        guard let re = try? NSRegularExpression(pattern: #"\{(\w+)\}"#) else { return [] }
        let ns = self as NSString
        return re.matches(in: self, range: NSRange(location: 0, length: ns.length))
            .compactMap { m in
                m.range(at: 1).location != NSNotFound ? ns.substring(with: m.range(at: 1)) : nil
            }
    }
}
