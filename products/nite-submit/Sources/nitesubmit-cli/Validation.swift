import Foundation
import NiteSubmitCore

// Real-document validation harness (privacy-safe, local-only).
//
// Manifest schema (real_manifest.json):
// {
//   "cases": [
//     { "id": "case_001",
//       "pdf": "/absolute/path/to/private.pdf",   // never copied into results
//       "category": "report",                     // optional diversity tag
//       "truth": {                                // genuinely absent fields use
//         "student_name": "...",                  // the literal value "ABSENT"
//         "student_id": "UNREVIEWED" } }          // omit/UNREVIEWED = skip field
//   ]
// }
//
// Results contain anonymous case IDs and status codes only — never document
// text, personal values or private paths of the underlying documents.

struct ValidationCase: Decodable {
    let id: String
    let pdf: String
    let category: String?
    /// `layout_only` keeps official guidance/templates in extraction smoke
    /// tests without counting their prose as student-submission truth.
    let evaluationMode: String?
    let truth: [String: String]

    private enum CodingKeys: String, CodingKey {
        case id, pdf, category, evaluationMode = "evaluation_mode", truth
    }
}
struct ValidationManifest: Decodable { let cases: [ValidationCase] }

let fieldNames = ["student_name", "student_id", "university", "module_code", "project_title"]

/// Resolve manifests created on another checkout without weakening the
/// privacy boundary. Absolute paths are used when valid; otherwise only the
/// known `real_validation_corpus/` suffix is relocated under the current
/// project directory.
func resolveManifestPDF(_ path: String) -> URL {
    let direct = URL(fileURLWithPath: path)
    if FileManager.default.fileExists(atPath: direct.path) { return direct }
    guard let marker = path.range(of: "real_validation_corpus/") else { return direct }
    let suffix = String(path[marker.upperBound...])
    return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        .appendingPathComponent("real_validation_corpus", isDirectory: true)
        .appendingPathComponent(suffix)
}

func detection(_ meta: SubmissionMetadata, _ field: String) -> Detection {
    switch field {
    case "student_name": return meta.studentName
    case "student_id": return meta.studentId
    case "university": return meta.university
    case "module_code": return meta.moduleCode
    case "project_title": return meta.projectTitle
    default: return .missing()
    }
}

func isUnreviewed(_ v: String?) -> Bool {
    guard let value = v?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return true
    }
    let marker = value.uppercased()
    return marker == "UNREVIEWED" || marker == "REVIEW"
}

func isAbsent(_ v: String?) -> Bool {
    v?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() == "ABSENT"
}

func runValidation(manifestPath: String, outPath: String?) {
    let data = try! Data(contentsOf: URL(fileURLWithPath: manifestPath))
    let manifest = try! JSONDecoder().decode(ValidationManifest.self, from: data)
    let detector = FieldDetector()

    var tp: [String: Int] = [:], fp: [String: Int] = [:], fn: [String: Int] = [:]
    var absentOK: [String: Int] = [:]
    var highHits: [String: Int] = [:], highCorrect: [String: Int] = [:]
    var wrongHighCases: [[String: String]] = []
    var encryptedCount = 0, failed = 0, processed = 0
    var latencies: [Double] = []

    for c in manifest.cases {
        let url = resolveManifestPDF(c.pdf)
        guard FileManager.default.fileExists(atPath: url.path) else { failed += 1; continue }

        let t0 = CFAbsoluteTimeGetCurrent()
        var outcome: PDFExtractor.Outcome? = nil
        do { outcome = try PDFExtractor().extract(at: url) }
        catch { encryptedCount += 1 } // locked/unreadable docs count as unreadable
        latencies.append(CFAbsoluteTimeGetCurrent() - t0)
        processed += 1

        guard case .success(let doc)? = outcome else {
            if c.evaluationMode != "layout_only" {
                for f in fieldNames
                where !isUnreviewed(c.truth[f]) && !isAbsent(c.truth[f]) {
                    fn[f, default: 0] += 1
                }
            }
            continue
        }
        if c.evaluationMode == "layout_only" { continue }
        let meta = detector.detect(in: doc)

        for field in fieldNames {
            let truth = c.truth[field]
            // A missing truth key is intentionally not an absence claim. This
            // prevents partial review manifests from turning unknown fields
            // into false positives/negatives.
            if isUnreviewed(truth) { continue }
            let d = detection(meta, field)
            if isAbsent(truth) {
                if d.isMissing {
                    absentOK[field, default: 0] += 1
                } else {
                    fp[field, default: 0] += 1
                    if d.confidence == .high {
                        wrongHighCases.append(["id": c.id, "field": field,
                                               "got": "(withheld)", "wanted": "ABSENT",
                                               "rule": d.rule ?? ""])
                    }
                }
                continue
            }
            if d.isMissing { fn[field, default: 0] += 1; continue }
            let correctNow = d.value!.caseInsensitiveCompare(truth!) == .orderedSame
            if correctNow { tp[field, default: 0] += 1 } else { fp[field, default: 0] += 1 }
            if d.confidence == .high {
                highHits[field, default: 0] += 1
                if correctNow { highCorrect[field, default: 0] += 1 }
                if !correctNow {
                    wrongHighCases.append(["id": c.id, "field": field,
                                           "got": "(withheld)", "wanted": "(truth withheld)",
                                           "rule": d.rule ?? ""])
                }
            }
        }
    }

    latencies.sort()
    func pct(_ n: Int, _ d: Int) -> String {
        d == 0 ? "n/a" : String(format: "%.4f", Double(n) / Double(d))
    }
    func percentile(_ q: Double) -> String {
        guard !latencies.isEmpty else { return "n/a" }
        let i = min(latencies.count - 1, Int((q / 100.0) * Double(latencies.count - 1)))
        return String(format: "%.4f", latencies[i])
    }
    var summary: [String: [String: String]] = [:]
    for f in fieldNames {
        summary[f] = [
            "precision": pct(tp[f] ?? 0, (tp[f] ?? 0) + (fp[f] ?? 0)),
            "recall": pct(tp[f] ?? 0, (tp[f] ?? 0) + (fn[f] ?? 0)),
            "high_confidence_precision": pct(highCorrect[f] ?? 0, highHits[f] ?? 0),
            "true_positives": "\(tp[f] ?? 0)",
            "false_positives": "\(fp[f] ?? 0)",
            "false_negatives": "\(fn[f] ?? 0)",
            "absent_correctly_ignored": "\(absentOK[f] ?? 0)",
        ]
    }

    let result: [String: Any] = [
        "corpus_id": "REAL_DOCUMENT_VALIDATION_V1",
        "privacy_note": "anonymous ids + status codes only; no document text or personal values",
        "processed": processed,
        "encrypted_or_unreadable": encryptedCount,
        "failed_missing_files": failed,
        "latency_p50_s": percentile(50), "latency_p95_s": percentile(95),
        "latency_p99_s": percentile(99), "latency_max_s": percentile(100),
        "wrong_high_confidence_total": wrongHighCases.count,
        "fields": summary,
    ]
    let jsonData = try! JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted])
    let target = outPath ?? "validation_results.json"
    try! jsonData.write(to: URL(fileURLWithPath: target))
    print("Wrote \(target)")
    print("processed=\(processed) encrypted_or_unreadable=\(encryptedCount) missing_files=\(failed)")
    print("WRONG HIGH-CONFIDENCE cases: \(wrongHighCases.count)")
    for w in wrongHighCases.prefix(20) { print("  \(w)") }
}


// Terminal review interface: keyboard-driven ground-truth confirmation, resumable.
func runReview(manifestPath: String, progressPath: String) {
    let data = try! Data(contentsOf: URL(fileURLWithPath: manifestPath))
    let manifest = try! JSONDecoder().decode(ValidationManifest.self, from: data)
    var progress: [String: [String: String]] = [:]
    if FileManager.default.fileExists(atPath: progressPath),
       let obj = try? JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: progressPath)))
           as? [String: [String: String]] {
        progress = obj
        print("Resuming: \(progress.count)/\(manifest.cases.count) cases already reviewed")
    }
    let detector = FieldDetector()

    func save() {
        let j = try! JSONSerialization.data(withJSONObject: progress, options: [.prettyPrinted])
        try! j.write(to: URL(fileURLWithPath: progressPath))
    }
    func ask(_ prompt: String) -> String {
        print(prompt, terminator: " ")
        return (readLine() ?? "s").lowercased()
    }

    for c in manifest.cases where progress[c.id] == nil {
        print("\n=== \(c.id)  category=\(c.category ?? "?") ===")
        var meta = SubmissionMetadata()
        let url = resolveManifestPDF(c.pdf)
        if let out = try? PDFExtractor().extract(at: url),
           case .success(let doc) = out {
            meta = detector.detect(in: doc)
        }
        var verdicts: [String: String] = [:]
        for field in fieldNames {
            let truth = c.truth[field] ?? "ABSENT"
            let d = detection(meta, field)
            print("  \(field):")
            print("    detected : \(d.isMissing ? "MISSING" : d.value!) [\(d.confidence.rawValue)] via \(d.rule ?? "-")")
            print("    expected : \(truth)")
            let a = ask("    verdict [c]orrect / [w]rong / [m]issing / [s]kip:")
            verdicts[field] = a.hasPrefix("c") ? "correct" : a.hasPrefix("w") ? "wrong"
                : a.hasPrefix("m") ? "missing" : "skipped"
        }
        progress[c.id] = verdicts
        save()
        print("  saved (\(progress.count)/\(manifest.cases.count))")
    }
    save()
    print("Review complete: \(progress.count)/\(manifest.cases.count).")
}
