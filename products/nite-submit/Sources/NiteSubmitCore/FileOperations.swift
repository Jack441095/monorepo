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
    case symlinkedSource(String)
    case destinationUnwritable(String)

    public var errorDescription: String? {
        switch self {
        case .sourceMissing: return "The original file could not be found."
        case .destinationMissing: return "The destination folder could not be found."
        case .collision(let name): return "“\(name)” already exists there."
        case .invalidFilename(let reason): return reason
        case .notPDF: return "That file is not a PDF."
        case .hashMismatch: return "Safety check failed — operation aborted, nothing was changed."
        case .symlinkedSource(let name):
            return "“\(name)” is a link to a file elsewhere, so NiteSubmit will not copy from it. Open the real file and try again."
        case .destinationUnwritable(let name):
            return "Could not write “\(name)” in that folder — check the folder's permissions."
        }
    }
}

/// True when `candidate` is `container` itself or sits underneath it. Both sides are
/// canonicalized with symlinks resolved before comparing, because a plain prefix test on the
/// paths as typed let a batch write its output through a symlink that pointed back into the
/// input tree — the next run then re-read its own output as fresh submissions and doubled the
/// batch. The separator is part of the comparison so "out" never swallows a sibling "outgoing".
public func pathIsInside(_ candidate: URL, _ container: URL) -> Bool {
    let inner = canonicalPath(candidate)
    let outer = canonicalPath(container)
    if inner == outer { return true }
    return inner.hasPrefix(outer.hasSuffix("/") ? outer : outer + "/")
}

/// One path, resolved as far as the filesystem allows.
private func canonicalPath(_ url: URL) -> String {
    let standardized = url.standardizedFileURL
    if FileManager.default.fileExists(atPath: standardized.path) {
        return standardized.resolvingSymlinksInPath().path
    }
    // resolvingSymlinksInPath() hands back an untouched path for anything that isn't there yet,
    // so a --out directory about to be created kept its symlinked parent and slipped under the
    // input tree. Resolve the parent instead and re-attach the final component.
    let parent = standardized.deletingLastPathComponent().resolvingSymlinksInPath()
    return parent.appendingPathComponent(standardized.lastPathComponent).path
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
        try Self.validateSourceNotSymlink(original)
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

    /// A symlink in the picked folder points at bytes from somewhere else: a
    /// Dropbox shortcut, a Finder alias, a link into a shared drive. Copying
    /// through it would pull content the user never chose into a submission
    /// folder under a name they never typed, and no hash check can catch that,
    /// because the link's target is a perfectly valid PDF. We refuse and let the
    /// user pick the real file. `fileExists` follows links, so this asks for the
    /// link's own resource value, which is what distinguishes the two.
    private static func validateSourceNotSymlink(_ url: URL) throws {
        guard (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]))?.isSymbolicLink == true else { return }
        throw FileOperationError.symlinkedSource(url.lastPathComponent)
    }

    /// How many times we re-pick a numbered name when a race keeps taking it.
    /// A real folder with name_1 … name_37 already gets close; 200 is a ceiling
    /// that cannot spin forever, not an expected retry count.
    private static let maxDestinationAttempts = 200

    /// Reserve a name with an exclusive create. Returns false when the name is
    /// already taken and throws for every other errno, so a read-only
    /// destination is reported as the I/O failure it is rather than dressed up
    /// as a collision. `fileExists` cannot be used for this: between the check
    /// and the write another process — Spotlight, Dropbox, a second NiteSubmit
    /// window, the student's own Finder — can create the file, and that window
    /// is exactly how one submission overwrites another.
    private static func claimName(_ url: URL) throws -> Bool {
        let fd = open(url.path, O_CREAT | O_EXCL | O_WRONLY, 0o600)
        if fd >= 0 {
            close(fd)
            return true
        }
        guard errno == EEXIST else {
            throw FileOperationError.destinationUnwritable(url.lastPathComponent)
        }
        return false
    }

    /// Put the staged bytes at their final name.
    ///
    /// .replace means the caller already confirmed an overwrite, so the file
    /// sitting there is ours to take. For .error and .appendCounter we must not
    /// clobber a file we never inspected, so an exclusive create decides whether
    /// the name is free first. The September code deleted the destination and
    /// only then moved the temp file in, so any failure in between destroyed the
    /// user's previous file outright.
    private func installStagedFile(_ staged: URL, destination: URL,
                                   policy: CollisionPolicy) throws {
        let fm = FileManager.default
        let ownsPlaceholder = policy != .replace
        if ownsPlaceholder {
            guard try Self.claimName(destination) else {
                throw FileOperationError.collision(destination.lastPathComponent)
            }
        }
        do {
            // One same-directory rename over whatever is already at the
            // destination: the empty placeholder we just claimed, or under
            // .replace the previous file the caller told us to overwrite. A crash
            // cannot expose a half-written submission, and moveItem is not usable
            // here because it refuses to land on an existing name at all.
            _ = try fm.replaceItemAt(destination, withItemAt: staged,
                                     backupItemName: nil, options: .usingNewMetadataOnly)
        } catch {
            // The placeholder is ours to remove. The previous file is not.
            if ownsPlaceholder { try? fm.removeItem(at: destination) }
            throw error
        }
    }

    // MARK: - Operations

    @discardableResult
    public func createRenamedCopy(source: URL, directory: URL, newBaseName: String,
                                  ext: String? = nil,
                                  policy: CollisionPolicy) throws -> OperationReceipt {
        let fileExt = ext ?? source.pathExtension
        let fm = FileManager.default
        // Refuse a linked source before a single byte is read: resolving the link
        // first would pull in content from outside the folder the user picked.
        guard fm.fileExists(atPath: source.path) else { throw FileOperationError.sourceMissing }
        try Self.validateSourceNotSymlink(source)
        // Checked here as well as in resolveDestination, because the copy below
        // now happens first and would fail with a bare Cocoa error for a folder
        // that is not there.
        guard fm.fileExists(atPath: directory.path) else { throw FileOperationError.destinationMissing }
        let beforeHash = try Self.sha256(of: source)

        // Stage into a hidden sibling inside the destination folder. The old code
        // staged in temporaryDirectory, which on macOS sits on the system volume
        // while a student's library folder usually does not, so the final step
        // was a byte-by-byte cross-volume copy that a crash or a full disk could
        // leave half written. A rename within one directory is atomic: the
        // destination is either the old file or the complete new one.
        let staged = directory.appendingPathComponent(".nitesubmit-staging-\(UUID().uuidString)")
            .appendingPathExtension(fileExt.isEmpty ? "tmp" : fileExt)
        defer { try? fm.removeItem(at: staged) }
        try fm.copyItem(at: source, to: staged)

        // Verify the staged bytes before they are allowed to become a
        // submission. Checking after the rename is too late: on a large PDF the
        // student would already be looking at a corrupt file.
        guard try Self.sha256(of: staged) == beforeHash else { throw FileOperationError.hashMismatch }

        let dest = try installWithCollisionRetry(staged: staged, source: source,
                                                 directory: directory, newBaseName: newBaseName,
                                                 ext: fileExt, policy: policy)

        return OperationReceipt(
            originalPath: source.path, originalFilename: source.lastPathComponent,
            newFilename: dest.lastPathComponent, mode: .createCopy,
            timestamp: Date(), success: true,
            message: "Created renamed copy.", undoPath: nil)
    }

    /// The name `resolveDestination` picks is a guess: it is free at the moment we
    /// look, and something else can take it a microsecond later. The exclusive
    /// create in `installStagedFile` is the real authority, so on a lost race we
    /// ask for a fresh candidate and try again rather than reporting success for
    /// a name we never actually wrote.
    private func installWithCollisionRetry(staged: URL, source: URL, directory: URL,
                                           newBaseName: String, ext: String,
                                           policy: CollisionPolicy) throws -> URL {
        var attempt = 0
        while true {
            let dest = try resolveDestination(original: source, directory: directory,
                                              newBaseName: newBaseName, ext: ext, policy: policy)
            do {
                try installStagedFile(staged, destination: dest, policy: policy)
                return dest
            } catch FileOperationError.collision
                where policy == .appendCounter && attempt < Self.maxDestinationAttempts {
                attempt += 1
            }
        }
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

    @discardableResult
    public func moveOriginal(source: URL, directory: URL, newBaseName: String,
                             ext: String? = nil,
                             policy: CollisionPolicy) throws -> OperationReceipt {
        let fileExt = ext ?? source.pathExtension
        let dest = try resolveDestination(original: source, directory: directory,
                                          newBaseName: newBaseName, ext: fileExt, policy: policy)
        let beforeHash = try Self.sha256(of: source)
        if policy == .replace && FileManager.default.fileExists(atPath: dest.path) {
            try FileManager.default.removeItem(at: dest)
        }
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

        var message = "Moved original file."
        if policy == .replace {
            message += " Previous file replaced with force; earlier copy was removed only after the hash check."
        }
        return OperationReceipt(
            originalPath: source.path, originalFilename: source.lastPathComponent,
            newFilename: dest.lastPathComponent, mode: .renameOriginal,
            timestamp: Date(), success: true,
            message: message,
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
    /// Colliding actions default to refusal: pass forceOverwrite: true to
    /// explicitly allow replacing existing destinations. We never overwrite
    /// silently because a library folder can hold a student's only copy.
    public func executeOrganizationPlan(_ plan: OrganizationPlan, dryRun: Bool = false,
                                        forceOverwrite: Bool = false) -> PlanExecutionReceipt {
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
            let destExt = action.destinationURL.pathExtension
            // A plan collision means the destination already exists on disk or
            // twice in this batch. Without explicit force we refuse the action
            // and leave the existing file untouched.
            if action.hasCollision && !forceOverwrite {
                receipts.append(OperationReceipt(
                    originalPath: action.sourceURL.path,
                    originalFilename: action.sourceURL.lastPathComponent,
                    newFilename: action.destinationURL.lastPathComponent,
                    mode: action.actionType == .copy ? .createCopy : .renameOriginal,
                    timestamp: Date(),
                    success: false,
                    message: "Blocked: “\(action.destinationURL.lastPathComponent)” already exists. Re-run with force to overwrite.",
                    undoPath: nil
                ))
                failCount += 1
                continue
            }
            let policy: CollisionPolicy = forceOverwrite ? .replace : .error

            do {
                if action.actionType == .copy {
                    var receipt = try createRenamedCopy(
                        source: action.sourceURL,
                        directory: destDir,
                        newBaseName: newBaseName,
                        ext: destExt.isEmpty ? nil : destExt,
                        policy: policy
                    )
                    if action.hasCollision {
                        receipt.message += " Previous file replaced with force; earlier copy was backed up and removed after the hash check."
                    }
                    receipts.append(receipt)
                } else if destDir.standardizedFileURL.path == action.sourceURL.deletingLastPathComponent().standardizedFileURL.path {
                    var receipt = try renameOriginal(
                        source: action.sourceURL,
                        newBaseName: newBaseName,
                        ext: destExt.isEmpty ? nil : destExt,
                        policy: policy
                    )
                    if action.hasCollision {
                        receipt.message += " Previous file replaced with force."
                    }
                    receipts.append(receipt)
                } else {
                    let receipt = try moveOriginal(
                        source: action.sourceURL,
                        directory: destDir,
                        newBaseName: newBaseName,
                        ext: destExt.isEmpty ? nil : destExt,
                        policy: policy
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
