import Foundation
import NiteSubmitCore

// CLI for evaluation, benchmarks and scripted use. Fully local.
let args = CommandLine.arguments

func usage() -> Never {
    print("""
    nitesubmit-cli — NITE Submit command-line interface (local only)

    USAGE:
      nitesubmit-cli suggest <file.pdf> [--template "<tpl>"] [--student-id <id>]
      nitesubmit-cli copy    <file.pdf> --to <dir> --name <basename> [--policy error|counter|replace]
      nitesubmit-cli rename  <file.pdf> --name <basename> [--policy ...]
      nitesubmit-cli pack    <files...> --out <archive.7z> [--format 7z|zip|tar.gz] [--level store|fast|normal|maximum]
      nitesubmit-cli optimize <file.pdf> --out <output.pdf>  (lossless; writes a new file, never overwrites the source)
      nitesubmit-cli batch   <input-dir> --out <output-dir> [--template "<tpl>"] [--student-id <id>] [--collision error|counter] [--dry-run] [--approved-manifest approvals.json]
                         [--identity-policy no-rule|name-required|name-prohibited]
                         default template: {student_id}_{project_title}
      nitesubmit-cli organize <input-dir> [--rule category|date|custom] [--template "<tpl>"] [--to <output-dir>] [--dry-run] [--json]
      nitesubmit-cli validate --manifest real_manifest.json [--out results.json]
      nitesubmit-cli review   --manifest real_manifest.json [--progress progress.json]

    """)
    exit(0)
}

guard args.count >= 2 else { usage() }

switch args[1] {
case "suggest":
    guard args.count >= 3 else { usage() }
    let url = URL(fileURLWithPath: args[2])
    var template: String? = nil
    if let i = args.firstIndex(of: "--template"), i + 1 < args.count { template = args[i + 1] }
    let defaultStudentId = args.firstIndex(of: "--student-id").flatMap {
        $0 + 1 < args.count ? args[$0 + 1] : nil
    }
    do {
        switch try PDFExtractor().extract(at: url) {
        case .imageOnly:
            print("IMAGE-ONLY / OCR REQUIRED — enter fields manually.")
        case .success(let doc):
            var meta = FieldDetector().detect(in: doc)
            if meta.studentId.isMissing,
               let defaultStudentId,
               !defaultStudentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                meta.studentId = Detection(value: defaultStudentId,
                                           confidence: .high,
                                           source: "Applied from the supplied test student number",
                                           rule: "saved_default_student_id")
            }
            print("text_source:    \(doc.textOrigin.rawValue)")
            print("student_name:   \(meta.studentName.value ?? "MISSING") [\(meta.studentName.confidence.rawValue.uppercased())]")
            print("student_id:     \(meta.studentId.value ?? "MISSING") [\(meta.studentId.confidence.rawValue.uppercased())]")
            print("candidate_num:  \(meta.candidateNumber.value ?? "MISSING") [\(meta.candidateNumber.confidence.rawValue.uppercased())]")
            print("group_id:       \(meta.groupId.value ?? "MISSING") [\(meta.groupId.confidence.rawValue.uppercased())]")
            print("university:     \(meta.university.value ?? "MISSING") [\(meta.university.confidence.rawValue.uppercased())]")
            print("module_code:    \(meta.moduleCode.value ?? "MISSING") [\(meta.moduleCode.confidence.rawValue.uppercased())]")
            print("module_title:   \(meta.moduleTitle.value ?? "MISSING") [\(meta.moduleTitle.confidence.rawValue.uppercased())]")
            print("project_title:  \(meta.projectTitle.value ?? "MISSING") [\(meta.projectTitle.confidence.rawValue.uppercased())]")
            if !meta.projectTitle.candidates.isEmpty {
                print("title candidates: \(meta.projectTitle.candidates.joined(separator: " | "))")
            }
            if let tpl = template {
                let values = meta.variableMap()
                if let rendered = TemplateEngine.render(template: tpl, values: values,
                                                        originalName: url.deletingPathExtension().lastPathComponent) {
                    print("preview:        \(rendered).pdf")
                } else {
                    for m in TemplateEngine.missingRequiredFields(tpl, values: values) { print("BLOCKED: \(m)") }
                }
            }
        }
    } catch let e as LocalizedError {
        FileHandle.standardError.write((e.errorDescription ?? "Failed.").data(using: .utf8)!)
        exit(1)
    } catch {
        print("We couldn't read this PDF.")
        exit(1)
    }

case "copy", "rename":
    guard args.count >= 5, let toIdx = args.firstIndex(of: "--name"), toIdx + 1 < args.count else { usage() }
    let name = args[toIdx + 1]
    var policy: CollisionPolicy = .error
    if let pIdx = args.firstIndex(of: "--policy"), pIdx + 1 < args.count,
       let p = CollisionPolicy(rawValue: "appendCounter".lowercased().contains(args[pIdx + 1]) ? "appendCounter" : args[pIdx + 1]) {
        policy = p
    } else if let pIdx = args.firstIndex(of: "--policy"), pIdx + 1 < args.count {
        policy = args[pIdx + 1] == "counter" ? .appendCounter : CollisionPolicy(rawValue: args[pIdx + 1]) ?? .error
    }
    let op = FileOperator()
    do {
        let receipt: OperationReceipt
        if args[1] == "copy" {
            var dir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            if let dIdx = args.firstIndex(of: "--to"), dIdx + 1 < args.count {
                dir = URL(fileURLWithPath: args[dIdx + 1])
            }
            receipt = try op.createRenamedCopy(source: URL(fileURLWithPath: args[2]),
                                               directory: dir, newBaseName: name, policy: policy)
        } else {
            receipt = try op.renameOriginal(source: URL(fileURLWithPath: args[2]),
                                            newBaseName: name, policy: policy)
        }
        print("\(receipt.message) → \(receipt.newFilename ?? "?")")
    } catch let e as LocalizedError {
        FileHandle.standardError.write((e.errorDescription ?? "Failed.").data(using: .utf8)!)
        exit(1)
    }

case "pack":
    guard let outIdx = args.firstIndex(of: "--out"), outIdx + 1 < args.count else { usage() }
    let archivePath = args[outIdx + 1]
    let inputFiles = Array(args.dropFirst(2).prefix(while: { !$0.hasPrefix("--") }))
    guard !inputFiles.isEmpty else { usage() }

    let formatRaw = args.firstIndex(of: "--format").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } ?? "7z"
    let format = ArchiveFormat(rawValue: formatRaw) ?? .sevenZip

    let levelRaw = args.firstIndex(of: "--level").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } ?? "normal"
    let level = CompressionLevel(rawValue: levelRaw) ?? .normal

    let password = args.firstIndex(of: "--password").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }

    let splitMb = args.firstIndex(of: "--volume-split-mb").flatMap { $0 + 1 < args.count ? Int64(args[$0 + 1]) : nil }
    let volumeSplit: VolumeSplitOption = {
        guard let mb = splitMb else { return .singleFile }
        switch mb {
        case 25: return .mb25
        case 100: return .mb100
        case 500: return .mb500
        case 1000, 1024: return .gb1
        case 2000, 2048: return .gb2
        default: return .singleFile
        }
    }()

    let sourceURLs = inputFiles.map { URL(fileURLWithPath: $0) }
    let destURL = URL(fileURLWithPath: archivePath)

    do {
        let receipt = try ArchiveEngine().compress(sources: sourceURLs, destinationArchive: destURL, format: format, level: level, password: password, volumeSplit: volumeSplit)
        let formattedSize = ByteCountFormatter.string(fromByteCount: receipt.archiveSizeBytes, countStyle: .file)
        var details = [] as [String]
        if receipt.isEncrypted { details.append("AES-256 Encrypted") }
        if receipt.isSplitVolume { details.append("Multi-Volume") }
        let extra = details.isEmpty ? "" : " [\(details.joined(separator: ", "))]"
        print("Created \(receipt.format.displayName)\(extra): \(receipt.archiveURL.path) (\(formattedSize)) [SHA-256: \(receipt.sha256Checksum)]")
    } catch {
        FileHandle.standardError.write("Failed to create archive: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }

case "optimize":
    // Deliberately separate from copy/rename: those guarantee byte-identical output (verified
    // SHA-256 before/after) because that is this app's core safety promise. Optimization
    // intentionally produces a *different*, smaller file with the same visible content — it must
    // never be silently folded into the byte-preserving path, so it always writes to an explicit
    // --out path rather than modifying the source in place.
    guard args.count >= 3,
          let outIdx = args.firstIndex(of: "--out"), outIdx + 1 < args.count else { usage() }
    let sourceURL = URL(fileURLWithPath: args[2])
    let destURL = URL(fileURLWithPath: args[outIdx + 1])
    do {
        let receipt = try PDFOptimizer().optimize(source: sourceURL, destination: destURL)
        let origSize = ByteCountFormatter.string(fromByteCount: receipt.originalSizeBytes, countStyle: .file)
        let optSize = ByteCountFormatter.string(fromByteCount: receipt.optimizedSizeBytes, countStyle: .file)
        print("Optimized \(sourceURL.lastPathComponent): \(origSize) -> \(optSize) (\(String(format: "%.1f", receipt.percentSaved))% smaller) [SHA-256: \(receipt.sha256Checksum)]")
        print("Output: \(receipt.outputURL.path)")
    } catch {
        FileHandle.standardError.write("Failed to optimize PDF: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }

case "batch":
    guard args.count >= 3,
          let outIdx = args.firstIndex(of: "--out"), outIdx + 1 < args.count else { usage() }
    let template = args.firstIndex(of: "--template").flatMap {
        $0 + 1 < args.count ? args[$0 + 1] : nil
    } ?? "{student_id}_{project_title}"
    let studentId = args.firstIndex(of: "--student-id").flatMap {
        $0 + 1 < args.count ? args[$0 + 1] : nil
    }
    let dryRun = args.contains("--dry-run")
    let approvedManifest = args.firstIndex(of: "--approved-manifest").flatMap {
        $0 + 1 < args.count ? args[$0 + 1] : nil
    }
    let approvedSources = loadApprovedSources(approvedManifest)
    var identityPolicy: DocumentIdentityPolicy = .noRule
    if let i = args.firstIndex(of: "--identity-policy") {
        guard i + 1 < args.count else {
            FileHandle.standardError.write(Data("--identity-policy needs a value.\n".utf8))
            exit(2)
        }
        switch args[i + 1].lowercased() {
        case "no-rule", "none", "no_rule": identityPolicy = .noRule
        case "name-required", "required", "name_required": identityPolicy = .nameRequired
        case "name-prohibited", "anonymous", "name_prohibited": identityPolicy = .nameProhibited
        default:
            FileHandle.standardError.write(Data("Unknown identity policy. Use no-rule, name-required, or name-prohibited.\n".utf8))
            exit(2)
        }
    }
    let collisionPolicy: CollisionPolicy = {
        guard let i = args.firstIndex(of: "--collision"), i + 1 < args.count else {
            return .appendCounter
        }
        return args[i + 1].lowercased() == "error" ? .error : .appendCounter
    }()
    guard runBatch(inputPath: args[2], outputPath: args[outIdx + 1],
                   template: template, defaultStudentId: studentId, dryRun: dryRun,
                   collisionPolicy: collisionPolicy, approvedSources: approvedSources,
                   identityPolicy: identityPolicy) else {
        exit(2)
    }

case "organize":
    guard args.count >= 3 else { usage() }
    let rule = args.firstIndex(of: "--rule").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } ?? "category"
    let template = args.firstIndex(of: "--template").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
    let destPath = args.firstIndex(of: "--to").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
    let dryRun = args.contains("--dry-run")
    let jsonOutput = args.contains("--json")

    guard runOrganize(directoryPath: args[2], ruleRaw: rule, customTemplate: template,
                        destinationPath: destPath, dryRun: dryRun, jsonOutput: jsonOutput) else {
        exit(2)
    }

case "validate", "review":
    guard let mIdx = args.firstIndex(of: "--manifest"), mIdx + 1 < args.count else { usage() }
    let outIdx = args.firstIndex(of: "--out").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
    if args[1] == "validate" {
        runValidation(manifestPath: args[mIdx + 1], outPath: outIdx)
    } else {
        var prog = "review_progress.json"
        if let pIdx = args.firstIndex(of: "--progress"), pIdx + 1 < args.count { prog = args[pIdx + 1] }
        runReview(manifestPath: args[mIdx + 1], progressPath: prog)
    }

default:
    usage()
}
