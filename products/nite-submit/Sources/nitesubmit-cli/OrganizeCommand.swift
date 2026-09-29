import Foundation
import NiteSubmitCore

func runOrganize(
    directoryPath: String,
    ruleRaw: String,
    customTemplate: String?,
    destinationPath: String?,
    dryRun: Bool,
    jsonOutput: Bool,
    forceOverwrite: Bool = false
) -> Bool {
    let dirURL = URL(fileURLWithPath: directoryPath)
    let fm = FileManager.default
    var isDir: ObjCBool = false

    guard fm.fileExists(atPath: dirURL.path, isDirectory: &isDir), isDir.boolValue else {
        FileHandle.standardError.write("Error: Directory not found at \(directoryPath)\n".data(using: .utf8)!)
        return false
    }

    let ruleType: OrganizationRuleType
    switch ruleRaw.lowercased() {
    case "by-category", "category", "by-extension", "extension":
        ruleType = .groupByCategory
    case "date-prefix", "date":
        ruleType = .datePrefix
    case "custom", "template":
        ruleType = .customTemplate(template: customTemplate ?? "{category}/{filename}")
    default:
        // An unknown rule must never silently become group-by-category;
        // the caller would tidy into folders they never asked for.
        FileHandle.standardError.write("Unknown --rule \"\(ruleRaw)\". Use category, date, or custom.\n".data(using: .utf8)!)
        return false
    }

    do {
        let scanner = FolderScanner()
        let manifest = try scanner.scan(directoryURL: dirURL)

        let engine = OrganizationRulesEngine()
        let destURL = destinationPath != nil ? URL(fileURLWithPath: destinationPath!) : nil
        let plan = engine.generatePlan(manifest: manifest, ruleType: ruleType, destinationDirectory: destURL, copyMode: true)

        let op = FileOperator()
        let receipt = op.executeOrganizationPlan(plan, dryRun: dryRun, forceOverwrite: forceOverwrite)

        if jsonOutput {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            encoder.dateEncodingStrategy = .iso8601
            if let data = try? encoder.encode(receipt), let jsonStr = String(data: data, encoding: .utf8) {
                print(jsonStr)
            }
        } else {
            let modeTag = dryRun ? "[DRY-RUN] " : ""
            print("== \(modeTag)Library Folder Organizer ==")
            print("Target Directory: \(plan.targetDirectory.path)")
            print("Rule Applied:     \(plan.ruleType.displayName)")
            print("Total Files:      \(plan.totalFilesToProcess)")
            print("Collisions:       \(plan.collisionsCount)")
            print("----------------------------------------")
            for action in plan.actions {
                let status = action.hasCollision ? "[COLLISION]" : "[OK]"
                print("\(status) \(action.sourceURL.lastPathComponent) -> \(action.destinationURL.path)")
            }
            print("----------------------------------------")
            print("Summary: \(receipt.succeededCount) succeeded, \(receipt.failedCount) failed.")
        }
        return receipt.failedCount == 0
    } catch {
        FileHandle.standardError.write("Organize failed: \(error.localizedDescription)\n".data(using: .utf8)!)
        return false
    }
}
