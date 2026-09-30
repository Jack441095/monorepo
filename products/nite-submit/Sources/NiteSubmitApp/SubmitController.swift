import Foundation
import AppKit
#if canImport(NiteSubmitCore)
import NiteSubmitCore
#endif

/// Session state + orchestration for one document. Holds extracted metadata
/// in memory for the session only — never persisted, never logged.
final class SubmitController {
    private(set) var metadata = SubmissionMetadata()
    private(set) var documentClassification = DocumentClassification()
    private(set) var documentIdentityCheck = DocumentIdentityCheck()
    private(set) var sourceURL: URL?
    private(set) var reviewApproved = false
    var originalBaseName: String? { sourceURL?.deletingPathExtension().lastPathComponent }
    var hasLoadedDocument: Bool { sourceURL != nil }
    var settings: AppSettings
    private var lastRenameReceipt: OperationReceipt?
    /// Blocking document work — PDFKit parsing, Vision OCR, qpdf and 7z — runs here and lands
    /// back on the main thread in one hop. The extractor's own bounds (2,000 pages, plus OCR of
    /// the first 3 at 2,200 px) are seconds of CPU, and inline on the main thread the window
    /// stopped answering clicks for the whole read.
    private let workQueue = DispatchQueue(label: "com.nitedsp.nitesubmit.work", qos: .userInitiated)
    /// Background jobs in flight. Approve, Create and Archive stay disabled while this is
    /// non-zero, so a second click cannot fire a second write against a half-read document.
    private var busyJobCount = 0
    var isBusy: Bool { busyJobCount > 0 }
    /// Newest read wins. Clicking through the queue starts several reads back to back and only
    /// the last one describes the row now on screen, so earlier completions are dropped.
    private var readToken = 0
    weak var view: MainView?

    init(view: MainView?) {
        self.view = view
        settings = AppSettings.load()
    }

    func reset() {
        // Abandon any read still in flight: its completion would otherwise refill the fields
        // the user just cleared, under the filename of a session they thought they had ended.
        readToken += 1
        metadata = SubmissionMetadata()
        documentClassification = DocumentClassification()
        documentIdentityCheck = DocumentIdentityCheck()
        sourceURL = nil
        reviewApproved = false
        lastRenameReceipt = nil
        view?.undoButton.isEnabled = false
        view?.refreshFields()
    }

    /// Runs blocking document work off the main thread and calls back on it, holding Approve,
    /// Create and Archive disabled for the duration. Every PDF read, identity re-check, qpdf
    /// optimization and archive compression in this app goes through here.
    func performInBackground<T: Sendable>(_ work: @escaping () throws -> T,
                                          then: @escaping (Result<T, Error>) -> Void) {
        busyJobCount += 1
        view?.refreshReviewState()
        workQueue.async { [weak self] in
            let result = Result(catching: work)
            DispatchQueue.main.async {
                guard let self else { return }
                self.busyJobCount = max(0, self.busyJobCount - 1)
                self.view?.refreshReviewState()
                then(result)
            }
        }
    }

    // MARK: - Loading

    /// Reads any dropped file. PDFs go through PDFExtractor, everything else — wav, mp4, mov,
    /// zip, docx — through MediaExtractor. This is the only loading path: calling loadPDF
    /// directly left a dropped .mp4 in the queue with a row that could never load.
    func loadFile(at url: URL) {
        // The policy is snapshotted here, on the main thread, because settings can be saved
        // from a text-field callback at any moment and the work queue must not read them.
        let policy = settings.documentIdentityPolicy
        readToken += 1
        let token = readToken
        performInBackground({ try Self.readFile(at: url, policy: policy) }) { [weak self] result in
            guard let self, token == self.readToken else { return }
            switch result {
            case .success(let read): self.apply(read, url: url)
            case .failure(let error):
                self.alert((error as? LocalizedError)?.errorDescription ?? "We couldn't read this file.")
            }
        }
    }

    /// One read pass. Detection is a pure function of the document text plus the policy
    /// snapshot, so it runs on the work queue and is applied in a single hop.
    struct FileRead {
        var metadata: SubmissionMetadata
        var classification: DocumentClassification
        var identityCheck: DocumentIdentityCheck
        /// The rule this check was made under, so `apply` can spot a rule change mid-read.
        var identityPolicy: DocumentIdentityPolicy
        /// Set when a PDF has no usable text layer and the UI must ask for manual entry.
        var needsManualEntry = false
    }

    private static func readFile(at url: URL, policy: DocumentIdentityPolicy) throws -> FileRead {
        if url.pathExtension.lowercased() != "pdf" {
            return FileRead(metadata: MediaExtractor().extractMetadata(at: url),
                            classification: DocumentClassification(),
                            identityCheck: DocumentIdentityCheck(),
                            identityPolicy: policy)
        }
        switch try PDFExtractor().extract(at: url) {
        case .imageOnly:
            return FileRead(metadata: SubmissionMetadata(),
                            classification: DocumentClassification(),
                            identityCheck: identityCheckWithoutText(policy),
                            identityPolicy: policy,
                            needsManualEntry: true)
        case .success(let doc):
            let detector = FieldDetector()
            return FileRead(metadata: detector.detect(in: doc),
                            classification: detector.classifyDocument(in: doc),
                            identityCheck: detector.checkDocumentIdentity(in: doc, policy: policy),
                            identityPolicy: policy)
        }
    }

    /// What we can honestly say about a document whose text we could not read: nothing was
    /// checked under "no rule", and any real rule is unavailable rather than satisfied.
    private static func identityCheckWithoutText(_ policy: DocumentIdentityPolicy) -> DocumentIdentityCheck {
        guard policy != .noRule else { return DocumentIdentityCheck() }
        return DocumentIdentityCheck(policy: policy, status: .unavailable,
                                     evidence: "Could not verify the first two pages because this PDF has no usable text")
    }

    private func apply(_ read: FileRead, url: URL) {
        metadata = read.metadata
        documentClassification = read.classification
        documentIdentityCheck = read.identityCheck
        reviewApproved = false
        // A rename receipt belongs to the document that earned it. Carrying it into the next
        // load made "Undo Rename" on a freshly selected row restore a different file's name;
        // captureState()/restore() now keep each receipt with its own queue item.
        lastRenameReceipt = nil
        view?.undoButton.isEnabled = false
        applySavedStudentIdIfNeeded()
        sourceURL = url
        view?.refreshFields()
        // The identity rule may have moved while this read was in flight. The check we just
        // applied is the one the read started under, so re-run it against this document rather
        // than judging it by a rule the user has already switched off.
        if read.identityPolicy != settings.documentIdentityPolicy {
            setDocumentIdentityPolicy(settings.documentIdentityPolicy)
        }
        if read.needsManualEntry {
            view?.statusLabel.stringValue = "PDF read locally — enter or check the details before approving."
            alert("This PDF appears to be scanned or image-only.",
                  info: "Enter the details manually below — renaming still works.")
            return
        }
        view?.statusLabel.stringValue = url.pathExtension.lowercased() == "pdf"
            ? "PDF read locally — check the detected details before approving."
            : "\(FileKind.detect(url: url).displayName) loaded locally — check or enter details before approving."
    }

    // MARK: - Editing

    func setDefaultStudentId(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let usingSavedFallback = metadata.studentId.rule == "saved_default_student_id"
        settings.defaultStudentId = trimmed
        settings.save()

        if usingSavedFallback {
            if trimmed.isEmpty {
                metadata.studentId = .missing("Saved student number cleared")
            } else {
                applySavedStudentIdIfNeeded()
            }
            reviewApproved = false
            view?.refreshFields()
        } else if metadata.studentId.isMissing {
            applySavedStudentIdIfNeeded()
            reviewApproved = false
            view?.refreshFields()
        }
    }

    func setDocumentIdentityPolicy(_ policy: DocumentIdentityPolicy) {
        settings.documentIdentityPolicy = policy
        settings.save()
        guard let sourceURL else {
            if policy == .noRule { documentIdentityCheck = DocumentIdentityCheck() }
            invalidateReview()
            view?.refreshPreview()
            return
        }
        invalidateReview()
        // A new rule means re-reading the opening pages, which is a full extraction — same
        // cost as the initial load, so it runs on the work queue too.
        performInBackground({ Self.identityCheck(at: sourceURL, policy: policy) }) { [weak self] result in
            // The user may have moved to another queue row while this ran; that row's own
            // check is the one that matters, not this document's.
            guard let self, self.sourceURL == sourceURL else { return }
            if case .success(let check) = result { self.documentIdentityCheck = check }
            self.invalidateReview()
            self.view?.refreshPreview()
        }
    }

    private static func identityCheck(at url: URL, policy: DocumentIdentityPolicy) -> DocumentIdentityCheck {
        if let outcome = try? PDFExtractor().extract(at: url), case .success(let doc) = outcome {
            return FieldDetector().checkDocumentIdentity(in: doc, policy: policy)
        }
        return identityCheckWithoutText(policy)
    }

    func applySavedStudentIdIfNeeded() {
        guard metadata.studentId.isMissing,
              !settings.defaultStudentId.isEmpty else { return }
        metadata.studentId = Detection(value: settings.defaultStudentId,
                                       confidence: .high,
                                       source: "Applied from your saved student number",
                                       rule: "saved_default_student_id")
    }

    func setManualValue(_ value: String, for field: MetadataField) {
        let trimmed = value.trimmingCharacters(in: .whitespaces)
        reviewApproved = false
        if trimmed.isEmpty {
            metadata.setDetection(.missing("Cleared by user"), for: field)
        } else {
            metadata.setDetection(Detection(value: trimmed, confidence: .high,
                                            source: "Entered manually", rule: "manual"),
                                  for: field)
        }
    }

    func currentValues() -> [String: String] { metadata.variableMap() }

    func invalidateReview() {
        reviewApproved = false
        view?.refreshReviewState()
    }

    func reviewBlockingReason() -> String? {
        guard sourceURL != nil else { return "Drop a PDF or media file first." }
        let template = view?.templateField.stringValue ?? settings.template
        if let problem = TemplateEngine.validate(template).first { return problem }
        if settings.universityPresetId == "anonymous_candidate" {
            let nameFields = Set(["first_name", "last_name", "full_name"])
            if !nameFields.isDisjoint(with: Set(template.variables())) {
                return "Anonymous candidate profile cannot include a student name."
            }
        }
        if let identityReason = documentIdentityCheck.blockingReason {
            return identityReason
        }
        if let ambiguous = TemplateEngine.ambiguousRequiredFields(template, metadata: metadata).first {
            return "Multiple possible \(ambiguous.lowercased()) values detected. Choose the correct value before approving."
        }
        return TemplateEngine.missingRequiredFields(template, values: currentValues()).first
    }

    @discardableResult
    func approveReview() -> Bool {
        guard !isBusy else { return false }
        guard reviewBlockingReason() == nil else { return false }
        reviewApproved = true
        settings.template = view?.templateField.stringValue ?? settings.template
        settings.save()
        view?.refreshReviewState()
        return true
    }

    // MARK: - Operations

    func performOperation(_ mode: FileOperationMode, status: @escaping (String) -> Void) {
        guard let src = sourceURL else { status("Drop a file first."); return }
        guard let view = view else { return }
        guard !isBusy else { status("Still reading the file — try again in a moment."); return }
        guard reviewApproved else {
            status("Review the detected details and click Approve details first.")
            return
        }
        let tpl = view.templateField.stringValue
        if let p = TemplateEngine.validate(tpl).first { status(p); return }
        let values = currentValues()
        if let m = TemplateEngine.missingRequiredFields(tpl, values: values).first { status(m); return }
        guard let base = TemplateEngine.render(template: tpl, values: values,
                                               originalName: originalBaseName ?? "assignment") else {
            status("Could not build a filename from these fields."); return
        }

        let op = FileOperator()
        do {
            let receipt: OperationReceipt
            switch mode {
            case .createCopy:
                receipt = try op.createRenamedCopy(source: src,
                                                   directory: src.deletingLastPathComponent(),
                                                   newBaseName: base, policy: .error)
            case .renameOriginal:
                receipt = try op.renameOriginal(source: src, newBaseName: base, policy: .error)
            }
            if receipt.mode == .renameOriginal {
                lastRenameReceipt = receipt
                view.undoButton.isEnabled = true
                if let newFilename = receipt.newFilename {
                    sourceURL = src.deletingLastPathComponent()
                        .appendingPathComponent(newFilename)
                }
            } else {
                lastRenameReceipt = nil
                view.undoButton.isEnabled = false
            }
            settings.template = tpl
            settings.renameMode = mode
            settings.save()
            view.refreshPreview()
            status("\(receipt.message) \(receipt.newFilename ?? "")")
        } catch FileOperationError.collision(let name) {
            askCollision(name) { [weak self] useCounter in
                guard let self else { return }
                let p: CollisionPolicy = useCounter ? .appendCounter : .error
                do {
                    let receipt = try mode == .createCopy
                        ? op.createRenamedCopy(source: src, directory: src.deletingLastPathComponent(),
                                               newBaseName: base, policy: p)
                        : op.renameOriginal(source: src, newBaseName: base, policy: p)
                    if receipt.mode == .renameOriginal {
                        self.lastRenameReceipt = receipt
                        view.undoButton.isEnabled = true
                        if let newFilename = receipt.newFilename {
                            self.sourceURL = src.deletingLastPathComponent()
                                .appendingPathComponent(newFilename)
                        }
                    } else {
                        self.lastRenameReceipt = nil
                        view.undoButton.isEnabled = false
                    }
                    self.settings.template = tpl
                    self.settings.renameMode = mode
                    self.settings.save()
                    view.refreshPreview()
                    status("\(receipt.message) \(receipt.newFilename ?? "")")
                } catch let e as LocalizedError {
                    status(e.errorDescription ?? "Failed.")
                } catch { status("Failed.") }
            }
        } catch let e as LocalizedError {
            status(e.errorDescription ?? "Failed.")
        } catch {
            status("Failed.")
        }
    }

    func performArchiveOperation(sources: [URL], format: ArchiveFormat = .sevenZip, level: CompressionLevel = .normal, password: String? = nil, volumeSplit: VolumeSplitOption = .singleFile, status: @escaping (String) -> Void) {
        guard !sources.isEmpty else { status("No files selected to archive."); return }
        guard let view = view else { return }
        guard !isBusy else { status("Still working on the previous file — try again in a moment."); return }
        guard reviewApproved else {
            status("Review the detected details and click Approve details first.")
            return
        }
        let tpl = view.templateField.stringValue
        if let p = TemplateEngine.validate(tpl).first { status(p); return }
        let values = currentValues()
        if let m = TemplateEngine.missingRequiredFields(tpl, values: values).first { status(m); return }
        guard let base = TemplateEngine.render(template: tpl, values: values,
                                               originalName: originalBaseName ?? "submission_batch") else {
            status("Could not build an archive filename from these fields."); return
        }

        let outputDir = (sourceURL ?? sources[0]).deletingLastPathComponent()
        let archiveFilename = "\(base).\(format.fileExtension)"
        let destination = outputDir.appendingPathComponent(archiveFilename)

        // 7z at -mx9 over a few hundred MB holds the CPU for tens of seconds and qpdf's
        // output has to be flushed to disk either way, so neither belongs on the main thread.
        performInBackground({ try ArchiveEngine().compress(sources: sources,
                                                           destinationArchive: destination,
                                                           format: format, level: level,
                                                           password: password, volumeSplit: volumeSplit) }) { result in
            switch result {
            case .success(let receipt): status(Self.archiveMessage(receipt, requested: format))
            case .failure(let e): status((e as? LocalizedError)?.errorDescription ?? "Archive creation failed.")
            }
        }
    }

    private static func archiveMessage(_ receipt: ArchiveReceipt, requested: ArchiveFormat) -> String {
        let formattedSize = ByteCountFormatter.string(fromByteCount: receipt.archiveSizeBytes, countStyle: .file)
        // Use receipt.format, not the requested `format`: if 7z was requested but the 7z tool
        // isn't installed, ArchiveEngine falls back to a real ZIP rather than mislabeling a
        // ZIP as ".7z" — the status message must report what was actually produced.
        var msg = "Created \(receipt.format.displayName): \(receipt.archiveURL.lastPathComponent) (\(formattedSize))"
        if receipt.format != requested {
            msg += " — the 7z tool isn't installed on this Mac, so a ZIP was created instead"
        }
        // Every encrypted receipt is AES-256 via the 7z tool (7z archives use
        // it by definition, ZIPs get `-mem=AES256`) — ArchiveEngine refuses
        // an encrypted archive rather than falling back to ZipCrypto, so
        // this label always means AES-256 and never overstates the crypto.
        if receipt.isEncrypted { msg += " [AES-256 Encrypted]" }
        if receipt.isSplitVolume { msg += " [Multi-Volume]" }
        msg += " [SHA-256: \(receipt.sha256Checksum.prefix(8))...]"
        return msg
    }

    func performUndo(status: @escaping (String) -> Void) {
        guard let r = lastRenameReceipt else { return }
        do {
            try FileOperator().undo(r)
            lastRenameReceipt = nil
            view?.undoButton.isEnabled = false
            sourceURL = URL(fileURLWithPath: r.originalPath)
            view?.refreshPreview()
            status("Undone — original filename restored.")
        } catch let e as LocalizedError {
            status(e.errorDescription ?? "Undo failed.")
        } catch { status("Undo failed.") }
    }

    // MARK: - Dialogs

    func alert(_ message: String, info: String? = nil) {
        let a = NSAlert()
        a.messageText = message
        if let info { a.informativeText = info }
        NSApp.activate(ignoringOtherApps: true)
        a.runModal()
    }

    func askCollision(_ name: String, completion: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = "“\(name)” already exists"
        a.informativeText = "Keep a numbered copy instead?"
        a.addButton(withTitle: "Use Numbered Name")
        a.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        completion(a.runModal() == .alertFirstButtonReturn)
    }

    // MARK: - Per-document state (review queue)

    struct DocumentState {
        var metadata: SubmissionMetadata
        var documentClassification: DocumentClassification
        var documentIdentityCheck: DocumentIdentityCheck
        var sourceURL: URL?
        var reviewApproved: Bool
        var lastRenameReceipt: OperationReceipt?
    }

    func captureState() -> DocumentState {
        DocumentState(metadata: metadata,
                      documentClassification: documentClassification,
                      documentIdentityCheck: documentIdentityCheck,
                      sourceURL: sourceURL,
                      reviewApproved: reviewApproved,
                      lastRenameReceipt: lastRenameReceipt)
    }

    func restore(_ state: DocumentState) {
        metadata = state.metadata
        documentClassification = state.documentClassification
        documentIdentityCheck = state.documentIdentityCheck
        sourceURL = state.sourceURL
        reviewApproved = state.reviewApproved
        lastRenameReceipt = state.lastRenameReceipt
        view?.undoButton.isEnabled = lastRenameReceipt != nil
        view?.refreshFields()
    }
}
