import Foundation
import NiteSubmitCore

struct BatchResult: Codable {
    let source: String
    let status: String
    let output: String?
    let fields: [String: String]
    let confidence: [String: String]
    let gaps: [String]
}

/// Explicit human approvals for medium/low-confidence batch previews. The
/// manifest contains source labels only; it never supplies or overrides field
/// values. Required-field gaps still block a write.
struct BatchApprovalManifest: Decodable {
    let version: String
    let approvedSources: [String]

    private enum CodingKeys: String, CodingKey {
        case version = "approval_version"
        case approvedSources = "approved_sources"
    }
}

func loadApprovedSources(_ path: String?) -> Set<String> {
    guard let path else { return [] }
    do {
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let manifest = try JSONDecoder().decode(BatchApprovalManifest.self, from: data)
        guard manifest.version == "BATCH_APPROVAL_V1" else {
            FileHandle.standardError.write(Data("Approval manifest rejected: unsupported approval_version.\n".utf8))
            return []
        }
        return Set(manifest.approvedSources.map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty })
    } catch {
        FileHandle.standardError.write(Data("Approval manifest rejected: could not read or decode it.\n".utf8))
        return []
    }
}

@discardableResult
func runBatch(inputPath: String, outputPath: String, template: String,
              defaultStudentId: String?, dryRun: Bool = false,
              collisionPolicy: CollisionPolicy = .appendCounter,
              approvedSources: Set<String> = [],
              identityPolicy: DocumentIdentityPolicy = .noRule) -> Bool {
    if let problem = TemplateEngine.validate(template).first {
        FileHandle.standardError.write(Data("Batch blocked: \(problem)\n".utf8))
        return false
    }
    let input = URL(fileURLWithPath: inputPath).standardizedFileURL
    let output = URL(fileURLWithPath: outputPath).standardizedFileURL
    let fm = FileManager.default
    try! fm.createDirectory(at: output, withIntermediateDirectories: true)

    let sourceURLs = (fm.enumerator(at: input, includingPropertiesForKeys: nil,
                                    options: [.skipsHiddenFiles])?.compactMap { $0 as? URL } ?? [])
        .filter { $0.pathExtension.lowercased() == "pdf" }
        .filter { !$0.standardizedFileURL.path.hasPrefix(output.path + "/") }
        .sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }

    let detector = FieldDetector()
    let operator_ = FileOperator()
    var results: [BatchResult] = []
    var seenSourceLabels: Set<String> = []

    func relative(_ url: URL) -> String {
        let prefix = input.path.hasSuffix("/") ? input.path : input.path + "/"
        return url.path.hasPrefix(prefix) ? String(url.path.dropFirst(prefix.count)) : url.lastPathComponent
    }
    func fieldMap(_ meta: SubmissionMetadata) -> [String: String] {
        var fields: [String: String] = [:]
        if let v = meta.studentName.value { fields["student_name"] = v }
        // Include the derived components used by name-bearing templates so a
        // reviewer can audit the exact first/last-name values in the output
        // filename, especially for Chicago-style rules.
        let nameValues = meta.variableMap()
        if let v = nameValues["first_name"] { fields["first_name"] = v }
        if let v = nameValues["last_name"] { fields["last_name"] = v }
        if let v = meta.studentId.value { fields["student_id"] = v }
        if let v = meta.candidateNumber.value { fields["candidate_number"] = v }
        if let v = meta.assignmentCode.value { fields["assignment_code"] = v }
        if let v = meta.groupId.value { fields["group_id"] = v }
        if let v = meta.university.value { fields["university"] = v }
        if let v = meta.moduleCode.value { fields["module_code"] = v }
        if let v = meta.moduleTitle.value { fields["module_title"] = v }
        if let v = meta.projectTitle.value { fields["project_title"] = v }
        return fields
    }
    func confidenceMap(_ meta: SubmissionMetadata) -> [String: String] {
        [
            "student_name": meta.studentName.confidence.rawValue,
            "student_id": meta.studentId.confidence.rawValue,
            "candidate_number": meta.candidateNumber.confidence.rawValue,
            "assignment_code": meta.assignmentCode.confidence.rawValue,
            "group_id": meta.groupId.confidence.rawValue,
            "university": meta.university.confidence.rawValue,
            "module_code": meta.moduleCode.confidence.rawValue,
            "module_title": meta.moduleTitle.confidence.rawValue,
            "project_title": meta.projectTitle.confidence.rawValue,
        ]
    }

    for source in sourceURLs {
        let sourceLabel = relative(source)
        seenSourceLabels.insert(sourceLabel)
        do {
            guard case .success(let doc) = try PDFExtractor().extract(at: source) else {
                let identityCheck = DocumentIdentityCheck(
                    policy: identityPolicy,
                    status: identityPolicy == .noRule ? .notChecked : .unavailable,
                    evidence: identityPolicy == .noRule
                        ? "No document identity rule selected"
                        : "Could not verify the first two pages because this PDF has no usable text")
                results.append(BatchResult(source: sourceLabel, status: "image_only",
                                            output: nil,
                                            fields: [
                                                "document_type": "image_only",
                                                "document_reason": "No usable text layer; bounded OCR or manual entry required",
                                                "document_identity_policy": identityCheck.policy.rawValue,
                                                "document_identity_status": identityCheck.status.rawValue,
                                                "document_identity_reason": identityCheck.evidence
                                            ],
                                            confidence: [:],
                                            gaps: ["OCR/manual entry required"]))
                continue
            }
            var meta = detector.detect(in: doc)
            if meta.studentId.isMissing, let defaultStudentId,
               !defaultStudentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                meta.studentId = Detection(value: defaultStudentId,
                                           confidence: .high,
                                           source: "Applied from the supplied test student number",
                                           rule: "saved_default_student_id")
            }
            var fields = fieldMap(meta)
            let classification = detector.classifyDocument(in: doc)
            fields["document_type"] = classification.kind.rawValue
            if let reason = classification.reason { fields["document_reason"] = reason }
            let identityCheck = detector.checkDocumentIdentity(in: doc, policy: identityPolicy)
            fields["document_identity_policy"] = identityCheck.policy.rawValue
            fields["document_identity_status"] = identityCheck.status.rawValue
            fields["document_identity_reason"] = identityCheck.evidence
            let confidence = confidenceMap(meta)
            let values = meta.variableMap()
            let variables = Set(template.variables())
            var gaps: [String] = []
            let requiredVariables = [
                "first_name", "last_name", "full_name", "student_id", "candidate_number",
                "assignment_code", "group_id", "university", "module_code", "module_title",
                "project_title", "assignment_title"
            ]
            for variable in requiredVariables
            where variables.contains(variable) && (values[variable]?.isEmpty ?? true) {
                let field: String
                switch variable {
                case "first_name", "last_name", "full_name": field = "student_name"
                case "assignment_title": field = "project_title"
                default: field = variable
                }
                if !gaps.contains(field) { gaps.append(field) }
            }

            if let identityReason = identityCheck.blockingReason {
                results.append(BatchResult(source: sourceLabel, status: "review_required",
                                            output: nil, fields: fields,
                                            confidence: confidence,
                                            gaps: ["document_identity", identityReason]))
                continue
            }

            guard gaps.isEmpty,
                  let base = TemplateEngine.render(template: template,
                                                    values: values,
                                                    originalName: source.deletingPathExtension().lastPathComponent)
            else {
                results.append(BatchResult(source: sourceLabel, status: "review_required",
                                            output: nil, fields: fields,
                                            confidence: confidence, gaps: gaps))
                continue
            }

            let usesName = !variables.isDisjoint(with: ["first_name", "last_name", "full_name"])
            let guidanceReview = classification.kind == .guidanceTemplate
            let uncertain = guidanceReview ||
                (usesName && meta.studentName.confidence != .high) ||
                (variables.contains("student_id") && meta.studentId.confidence != .high) ||
                (variables.contains("candidate_number") && meta.candidateNumber.confidence != .high) ||
                (variables.contains("assignment_code") && meta.assignmentCode.confidence != .high) ||
                (variables.contains("group_id") && meta.groupId.confidence != .high) ||
                (variables.contains("project_title") && meta.projectTitle.confidence != .high)
            let explicitlyApproved = approvedSources.contains(sourceLabel)
            if dryRun {
                results.append(BatchResult(source: sourceLabel,
                                            status: "dry_run",
                                            output: base + ".pdf", fields: fields,
                                            confidence: confidence,
                                            gaps: explicitlyApproved ? ["explicit_approval"] :
                                                (guidanceReview ? ["guidance_template_review"] :
                                                 (uncertain ? ["medium_or_low_confidence_review"] : []))))
            } else if uncertain && !explicitlyApproved {
                // Batch mode follows the same approval boundary as the app:
                // show a usable preview, but never write an inferred filename
                // until a person has reviewed the medium/low-confidence fields.
                // Guidance/templates are always review-held as well: a
                // complete-looking example cover is not evidence that the
                // input is a student's submission.
                results.append(BatchResult(source: sourceLabel,
                                            status: "review_required",
                                            output: nil, fields: fields,
                                            confidence: confidence,
                                            gaps: [guidanceReview ? "guidance_template_review" :
                                                   "medium_or_low_confidence_review"]))
            } else {
                let receipt = try operator_.createRenamedCopy(source: source,
                                                              directory: output,
                                                              newBaseName: base,
                                                              policy: collisionPolicy)
                results.append(BatchResult(source: sourceLabel,
                                            status: "processed",
                                            output: receipt.newFilename, fields: fields,
                                            confidence: confidence,
                                            gaps: explicitlyApproved && uncertain ? ["explicit_approval"] : []))
            }
        } catch FileOperationError.collision(let name) {
            results.append(BatchResult(source: sourceLabel, status: "collision",
                                        output: nil,
                                        fields: [
                                            "document_type": "unavailable",
                                            "document_reason": "Output collision: \(name)"
                                        ],
                                        confidence: [:],
                                        gaps: ["output_collision", name]))
        } catch {
            results.append(BatchResult(source: sourceLabel, status: "failed",
                                        output: nil,
                                        fields: [
                                            "document_type": "unavailable",
                                            "document_reason": "Extraction or file operation failed"
                                        ],
                                        confidence: [:],
                                        gaps: ["extraction_or_copy_failed"]))
        }
    }

    let unusedApprovals = approvedSources.subtracting(seenSourceLabels)
    if !unusedApprovals.isEmpty {
        FileHandle.standardError.write(Data("Warning: \(unusedApprovals.count) approval source label(s) did not match the input batch.\n".utf8))
    }

    let reportURL = output.appendingPathComponent("batch_results.json")
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try! encoder.encode(results).write(to: reportURL, options: .atomic)

    // Keep a flat report for quick review in Numbers, Excel, or a text editor.
    // Values are escaped as CSV fields so titles and evidence gaps remain intact.
    func csvField(_ value: String) -> String {
        let escaped = value.replacingOccurrences(of: "\"", with: "\"\"")
        return "\"\(escaped)\""
    }
    let columns = ["source", "status", "output", "document_type", "document_reason", "document_identity_policy", "document_identity_status", "document_identity_reason", "student_name", "first_name", "last_name", "student_id",
                   "candidate_number", "assignment_code", "group_id", "university", "module_code",
                   "module_title", "project_title", "gaps"]
    var csv = columns.joined(separator: ",") + "\n"
    for result in results {
        let row = [
            result.source,
            result.status,
            result.output ?? "",
            result.fields["document_type"] ?? "",
            result.fields["document_reason"] ?? "",
            result.fields["document_identity_policy"] ?? "",
            result.fields["document_identity_status"] ?? "",
            result.fields["document_identity_reason"] ?? "",
            result.fields["student_name"] ?? "",
            result.fields["first_name"] ?? "",
            result.fields["last_name"] ?? "",
            result.fields["student_id"] ?? "",
            result.fields["candidate_number"] ?? "",
            result.fields["assignment_code"] ?? "",
            result.fields["group_id"] ?? "",
            result.fields["university"] ?? "",
            result.fields["module_code"] ?? "",
            result.fields["module_title"] ?? "",
            result.fields["project_title"] ?? "",
            result.gaps.joined(separator: " | ")
        ].map(csvField).joined(separator: ",")
        csv += row + "\n"
    }
    let csvURL = output.appendingPathComponent("batch_results.csv")
    try! csv.write(to: csvURL, atomically: true, encoding: .utf8)

    let processed = results.filter { $0.status == "processed" }.count
    let dry = results.filter { $0.status == "dry_run" }.count
    let review = results.filter { $0.status == "review_required" }.count
    let collision = results.filter { $0.status == "collision" }.count
    let failed = results.filter { $0.status == "failed" || $0.status == "image_only" }.count
    print("Batch complete: \(sourceURLs.count) PDFs\(dryRun ? " (dry run)" : "")")
    print("processed=\(processed) dry_run=\(dry) review_required=\(review) collisions=\(collision) failed_or_image_only=\(failed)")
    print("results=\(reportURL.path)")
    print("csv=\(csvURL.path)")
    return true
}
