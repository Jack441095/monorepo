import Foundation
import CryptoKit

/// Rename mode. V1 defaults to CREATE COPY — non-destructive by design.
public enum FileOperationMode: String, Codable, CaseIterable, Sendable {
    case createCopy = "create_copy"
    case renameOriginal = "rename_original"
}

/// How to resolve a destination that already exists.
public enum CollisionPolicy: String, Codable, CaseIterable, Sendable {
    case error            // refuse (safe default)
    case appendCounter    // name_1.pdf, name_2.pdf ...
    case replace          // only when the user explicitly confirms
}

public struct OperationReceipt: Codable, Sendable {
    public var originalPath: String
    public var originalFilename: String
    public var newFilename: String?
    public var mode: FileOperationMode
    public var timestamp: Date
    public var success: Bool
    public var message: String
    /// Set when a rename can be undone.
    public var undoPath: String?
}

public struct PlanExecutionReceipt: Codable, Sendable {
    public var timestamp: Date
    public var totalActions: Int
    public var succeededCount: Int
    public var failedCount: Int
    public var actionReceipts: [OperationReceipt]

    public init(timestamp: Date = Date(), totalActions: Int, succeededCount: Int, failedCount: Int, actionReceipts: [OperationReceipt]) {
        self.timestamp = timestamp
        self.totalActions = totalActions
        self.succeededCount = succeededCount
        self.failedCount = failedCount
        self.actionReceipts = actionReceipts
    }
}

public enum FileOperationError: Error, LocalizedError {
    case sourceMissing
    case destinationMissing
    case collision(String)
    case invalidFilename(String)
    case notPDF
    case hashMismatch

    public var errorDescription: String? {
        switch self {
        case .sourceMissing: return "The original file could not be found."
        case .destinationMissing: return "The destination folder could not be found."
        case .collision(let name): return "“\(name)” already exists there."
        case .invalidFilename(let reason): return reason
        case .notPDF: return "That file is not a PDF."
        case .hashMismatch: return "Safety check failed — operation aborted, nothing was changed."
        }
    }
}

/// Safe file operations: never silently destructive,
/// always verifying content preservation by hash.
public struct FileOperator: Sendable {
    public init() {}

    /// Resolve the final destination URL honouring the collision policy.
    public func resolveDestination(original: URL, directory: URL,
                                   newBaseName: String, ext: String = "pdf",
                                   policy: CollisionPolicy) throws -> URL {
        let fm = FileManager.default
        guard fm.fileExists(atPath: original.path) else { throw FileOperationError.sourceMissing }
        guard fm.fileExists(atPath: directory.path) else { throw FileOperationError.destinationMissing }
        if let reason = FilenameSanitizer.invalidBaseNameReason(newBaseName) {
            throw FileOperationError.invalidFilename(reason)
        }

        let dest = directory.appendingPathComponent(newBaseName).appendingPathExtension(ext)
        if dest.standardizedFileURL.path == original.standardizedFileURL.path {
            throw FileOperationError.invalidFilename("The new filename is the same as the original.")
        }

        switch policy {
        case .replace:
            return dest
        case .error:
            if fm.fileExists(atPath: dest.path) { throw FileOperationError.collision(dest.lastPathComponent) }
            return dest
        case .appendCounter:
            var candidate = dest
            var counter = 1
            while fm.fileExists(atPath: candidate.path) {
                candidate = directory.appendingPathComponent("\(newBaseName)_\(counter)")
                    .appendingPathExtension(ext)
                counter += 1
            }
            return candidate
        }
    }

    // MARK: - Operations

    @discardableResult
    public func createRenamedCopy(source: URL, directory: URL, newBaseName: String,
                                  ext: String? = nil,
                                  policy: CollisionPolicy) throws -> OperationReceipt {
        let fileExt = ext ?? source.pathExtension
        let dest = try resolveDestination(original: source, directory: directory,
                                          newBaseName: newBaseName, ext: fileExt, policy: policy)
        let beforeHash = try Self.sha256(of: source)

        // Copy to temp then move into place (crash-safe against partial copies).
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExt.isEmpty ? "tmp" : fileExt)
        let fm = FileManager.default
        let destinationExistedBefore = fm.fileExists(atPath: dest.path)
        var destinationInstalled = false
        let backup = policy == .replace && destinationExistedBefore
            ? dest.deletingLastPathComponent()
                .appendingPathComponent(".nitesubmit-backup-\(UUID().uuidString).\(fileExt)")
            : nil
        var backupCreated = false
        defer { try? fm.removeItem(at: tmp) }
        do {
            if let backup {
                try fm.moveItem(at: dest, to: backup)
                backupCreated = true
            }
            let copySource = source.resolvingSymlinksInPath()
            try fm.copyItem(at: copySource, to: tmp)
            if !fm.fileExists(atPath: dest.path) {
                try fm.moveItem(at: tmp, to: dest)
            } else {
                try fm.removeItem(at: dest)
                try fm.moveItem(at: tmp, to: dest)
            }
            destinationInstalled = true
            let afterHash = try Self.sha256(of: dest)
            guard beforeHash == afterHash else { throw FileOperationError.hashMismatch }
        } catch {
            if destinationInstalled {
                try? fm.removeItem(at: dest)
            }
            if backupCreated, let backup,
               fm.fileExists(atPath: backup.path),
               !fm.fileExists(atPath: dest.path) {
                try? fm.moveItem(at: backup, to: dest)
            }
            throw error
        }
        if let backup { try? fm.removeItem(at: backup) }

        return OperationReceipt(
            originalPath: source.path, originalFilename: source.lastPathComponent,
            newFilename: dest.lastPathComponent, mode: .createCopy,
            timestamp: Date(), success: true,
            message: "Created renamed copy.", undoPath: nil)
    }

    @discardableResult
    public func renameOriginal(source: URL, newBaseName: String,
                               ext: String? = nil,
                               policy: CollisionPolicy) throws -> OperationReceipt {
        let fileExt = ext ?? source.pathExtension
        let dest = try resolveDestination(original: source,
                                          directory: source.deletingLastPathComponent(),
                                          newBaseName: newBaseName, ext: fileExt, policy: policy)
        let beforeHash = try Self.sha256(of: source)
        try FileManager.default.moveItem(at: source, to: dest)
        do {
            let afterHash = try Self.sha256(of: dest)
            guard beforeHash == afterHash else { throw FileOperationError.hashMismatch }
        } catch {
            if FileManager.default.fileExists(atPath: dest.path),
               !FileManager.default.fileExists(atPath: source.path) {
                try? FileManager.default.moveItem(at: dest, to: source)
            }
            throw error
        }

        return OperationReceipt(
            originalPath: source.path, originalFilename: source.lastPathComponent,
            newFilename: dest.lastPathComponent, mode: .renameOriginal,
            timestamp: Date(), success: true,
            message: "Renamed original file.",
            undoPath: dest.path)
    }

    /// Undo a successful rename-original by moving it back.
    public func undo(_ receipt: OperationReceipt) throws {
        guard receipt.mode == .renameOriginal, receipt.success,
              let undoPath = receipt.undoPath else {
            throw FileOperationError.sourceMissing
        }
        let back = URL(fileURLWithPath: receipt.originalPath)
        if FileManager.default.fileExists(atPath: back.path) {
            throw FileOperationError.collision(back.lastPathComponent)
        }
        try FileManager.default.moveItem(atPath: undoPath, toPath: back.path)
    }

    /// Execute a full folder organization plan with optional dry-run mode.
    public func executeOrganizationPlan(_ plan: OrganizationPlan, dryRun: Bool = false) -> PlanExecutionReceipt {
        let fm = FileManager.default
        var receipts: [OperationReceipt] = []
        var successCount = 0
        var failCount = 0

        for action in plan.actions {
            if dryRun {
                receipts.append(OperationReceipt(
                    originalPath: action.sourceURL.path,
                    originalFilename: action.sourceURL.lastPathComponent,
                    newFilename: action.destinationURL.lastPathComponent,
                    mode: action.actionType == .copy ? .createCopy : .renameOriginal,
                    timestamp: Date(),
                    success: true,
                    message: "[DRY-RUN] Would \(action.actionType.rawValue) to \(action.destinationURL.path)",
                    undoPath: nil
                ))
                successCount += 1
                continue
            }

            let destDir = action.destinationURL.deletingLastPathComponent()
            if !fm.fileExists(atPath: destDir.path) {
                try? fm.createDirectory(at: destDir, withIntermediateDirectories: true)
            }

            let newBaseName = action.destinationURL.deletingPathExtension().lastPathComponent

            do {
                if action.actionType == .copy {
                    let receipt = try createRenamedCopy(
                        source: action.sourceURL,
                        directory: destDir,
                        newBaseName: newBaseName,
                        policy: .replace
                    )
                    receipts.append(receipt)
                } else {
                    let receipt = try renameOriginal(
                        source: action.sourceURL,
                        newBaseName: newBaseName,
                        policy: .replace
                    )
                    receipts.append(receipt)
                }
                successCount += 1
            } catch {
                receipts.append(OperationReceipt(
                    originalPath: action.sourceURL.path,
                    originalFilename: action.sourceURL.lastPathComponent,
                    newFilename: action.destinationURL.lastPathComponent,
                    mode: action.actionType == .copy ? .createCopy : .renameOriginal,
                    timestamp: Date(),
                    success: false,
                    message: "Failed: \(error.localizedDescription)",
                    undoPath: nil
                ))
                failCount += 1
            }
        }

        return PlanExecutionReceipt(
            timestamp: Date(),
            totalActions: plan.actions.count,
            succeededCount: successCount,
            failedCount: failCount,
            actionReceipts: receipts
        )
    }

    static func sha256(of url: URL) throws -> String {
        // Stream the hash in bounded chunks. A student submission can be a
        // very large PDF; safety verification should not duplicate the whole
        // file in memory just to compare two digests.
        let handle: FileHandle
        do {
            handle = try FileHandle(forReadingFrom: url)
        } catch {
            struct HashFail: Error {}
            throw HashFail()
        }
        defer { try? handle.close() }

        var hasher = SHA256()
        do {
            while let chunk = try handle.read(upToCount: 1_048_576), !chunk.isEmpty {
                hasher.update(data: chunk)
            }
        } catch {
            struct HashFail: Error {}
            throw HashFail()
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
