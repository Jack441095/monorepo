import Foundation
#if canImport(NiteSubmitCore)
    import NiteSubmitCore
#elseif canImport(NiteSubmit)
    import NiteSubmit
#endif

struct CorpusCase: Decodable {
    let id: String
    let truth: [String: String]
    let meta: [String: String]
}
struct CorpusManifest: Decodable { let cases: [CorpusCase] }

func corpusDir() -> URL {
    // Corpus lives in the repo under Sources/NiteSubmitTests/Fixtures/corpus.
    URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .appendingPathComponent("Fixtures/corpus")
}

func runCorpusAndFailureTests() {
    let dir = corpusDir()
    let manifest = try! JSONDecoder().decode(CorpusManifest.self,
                                             from: Data(contentsOf: dir.appendingPathComponent("manifest.json")))
    suite("PDF Corpus (NITE_SUBMIT_PDF_CORPUS_V1)") {
        check(manifest.cases.count >= 200, "corpus has 200+ cases (\(manifest.cases.count))")

        var extracted = 0
        var hits: [String: Int] = [:]
        var correct: [String: Int] = [:]
        var wrongHigh: [String: Int] = [:]
        var latencies: [Double] = []
        var mismatchDetails: [String] = []
        var missedDetails: [String] = []
        let detector = FieldDetector()
        let criticalFields = ["student_name", "student_id", "module_code"]

        for c in manifest.cases {
            if c.meta["malformed"] == "true" || c.meta["image_only"] == "true" { continue }
            let url = dir.appendingPathComponent("pdf").appendingPathComponent(c.id + ".pdf")
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            let t0 = CFAbsoluteTimeGetCurrent()
            guard case .success(let doc) = try? PDFExtractor().extract(at: url) else {
                check(false, "\(c.id): extraction unexpectedly failed")
                continue
            }
            latencies.append(CFAbsoluteTimeGetCurrent() - t0)
            extracted += 1
            let meta = detector.detect(in: doc)
            let got: [String: Detection] = [
                "student_name": meta.studentName,
                "student_id": meta.studentId,
                "university": meta.university,
                "module_code": meta.moduleCode,
                "project_title": meta.projectTitle,
            ]
            for (field, d) in got {
                guard let v = d.value, !v.isEmpty else {
                    if let t = c.truth[field], missedDetails.count < 40 {
                        missedDetails.append("[\(c.id)] \(field): expected '\(t)', detector found nothing")
                    }
                    continue
                }
                hits[field, default: 0] += 1
                if let t = c.truth[field] {
                    let nv = v.split(separator: " ").joined(separator: " ")
                    let nt = t.split(separator: " ").joined(separator: " ")
                    if nv.caseInsensitiveCompare(nt) == .orderedSame {
                        correct[field, default: 0] += 1
                    } else {
                        if d.confidence == .high { wrongHigh[field, default: 0] += 1 }
                        if mismatchDetails.count < 40 {
                            mismatchDetails.append("[\(c.id)] \(field): got '\(v)' (\(d.confidence.rawValue)), want '\(t)'")
                        }
                    }
                } else if d.confidence == .high && criticalFields.contains(field) {
                    wrongHigh[field, default: 0] += 1
                }
            }
        }
        check(extracted >= 150, "enough extractable PDFs ran (\(extracted))")

        func precision(_ f: String) -> Double {
            guard let h = hits[f], h > 0 else { return 1 }
            return Double(correct[f] ?? 0) / Double(h)
        }
        for d in mismatchDetails { print("   mismatch", d) }
        for d in missedDetails { print("   missed", d) }
        print("   CORPUS METRICS — extracted: \(extracted)")
        for f in ["student_name", "student_id", "university", "module_code", "project_title"] {
            print("   \(f): hits=\(hits[f] ?? 0) correct=\(correct[f] ?? 0) precision=\(precision(f)) wrongHigh=\(wrongHigh[f] ?? 0)")
        }
        if !latencies.isEmpty {
            print(String(format: "   latency: avg=%.4fs max=%.4fs",
                         latencies.reduce(0, +) / Double(latencies.count),
                         latencies.max()!))
        }
        for f in ["student_name", "student_id", "module_code"] {
            check(precision(f) >= 0.98, "\(f) precision >= 98%")
        }
        check(precision("project_title") >= 0.95, "project title precision >= 95%")
        let totalWrongHigh = wrongHigh.values.reduce(0, +)
        check(Double(totalWrongHigh) / Double(max(extracted, 1)) < 0.01,
              "wrong HIGH-confidence rate < 1%")
    }

    runFailureCaseTests(dir)
}
