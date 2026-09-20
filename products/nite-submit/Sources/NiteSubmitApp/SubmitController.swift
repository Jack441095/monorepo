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
    weak var view: MainView?

    init(view: MainView?) {
        self.view = view
        settings = AppSettings.load()
    }

    func reset() {
        metadata = SubmissionMetadata()
        documentClassification = DocumentClassification()
        documentIdentityCheck = DocumentIdentityCheck()
        sourceURL = nil
        reviewApproved = false
        lastRenameReceipt = nil
        view?.refreshFields()
    }

    // MARK: - Loading

    @discardableResult
    func loadFile(at url: URL) -> Bool {
        if url.pathExtension.lowercased() == "pdf" {
            return loadPDF(at: url)
        } else {
            metadata = MediaExtractor().extractMetadata(at: url)
            documentClassification = DocumentClassification()
            documentIdentityCheck = DocumentIdentityCheck()
            reviewApproved = false
            applySavedStudentIdIfNeeded()
            sourceURL = url
            view?.refreshFields()
            let kind = FileKind.detect(url: url).displayName
            view?.statusLabel.stringValue = "\(kind) loaded locally — check or enter details before approving."
            return true
        }
    }

    @discardableResult
    func loadPDF(at url: URL) -> Bool {
        do {
            switch try PDFExtractor().extract(at: url) {
            case .imageOnly:
                metadata = SubmissionMetadata()
                documentClassification = DocumentClassification()
                documentIdentityCheck = DocumentIdentityCheck(
                    policy: settings.documentIdentityPolicy,
                    status: settings.documentIdentityPolicy == .noRule ? .notChecked : .unavailable,
                    evidence: settings.documentIdentityPolicy == .noRule
                        ? "No document identity rule selected"
                        : "Could not verify the first two pages because this PDF has no usable text")
                reviewApproved = false
                applySavedStudentIdIfNeeded()
                sourceURL = url
                view?.refreshFields()
                view?.statusLabel.stringValue = "PDF read locally — enter or check the details before approving."
                alert("This PDF appears to be scanned or image-only.",
                      info: "Enter the details manually below — renaming still works.")
                return true
            case .success(let doc):
                metadata = FieldDetector().detect(in: doc)
                documentClassification = FieldDetector().classifyDocument(in: doc)
                documentIdentityCheck = FieldDetector().checkDocumentIdentity(
                    in: doc, policy: settings.documentIdentityPolicy)
                reviewApproved = false
                applySavedStudentIdIfNeeded()
                sourceURL = url
                view?.refreshFields()
                view?.statusLabel.stringValue = "PDF read locally — check the detected details before approving."
                return true
            }
        } catch let e as LocalizedError {
            alert(e.errorDescription ?? "We couldn't read this PDF.")
        } catch {
            alert("We couldn't read this PDF.")
        }
        return false
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
        if let sourceURL,
           let outcome = try? PDFExtractor().extract(at: sourceURL),
           case .success(let doc) = outcome {
            documentIdentityCheck = FieldDetector().checkDocumentIdentity(in: doc, policy: policy)
        } else if policy == .noRule {
            documentIdentityCheck = DocumentIdentityCheck()
        } else if sourceURL != nil {
            documentIdentityCheck = DocumentIdentityCheck(
                policy: policy, status: .unavailable,
                evidence: "Could not verify the first two pages because this PDF has no usable text")
        }
        invalidateReview()
        view?.refreshPreview()
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

        do {
            let receipt = try ArchiveEngine().compress(sources: sources, destinationArchive: destination, format: format, level: level, password: password, volumeSplit: volumeSplit)
            let formattedSize = ByteCountFormatter.string(fromByteCount: receipt.archiveSizeBytes, countStyle: .file)
            // Use receipt.format, not the requested `format`: if 7z was requested but the 7z tool
            // isn't installed, ArchiveEngine falls back to a real ZIP rather than mislabeling a
            // ZIP as ".7z" — the status message must report what was actually produced.
            var msg = "Created \(receipt.format.displayName): \(receipt.archiveURL.lastPathComponent) (\(formattedSize))"
            if receipt.format != format {
                msg += " — the 7z tool isn't installed on this Mac, so a ZIP was created instead"
            }
            if receipt.isEncrypted { msg += " [AES-256 Encrypted]" }
            if receipt.isSplitVolume { msg += " [Multi-Volume]" }
            msg += " [SHA-256: \(receipt.sha256Checksum.prefix(8))...]"
            status(msg)
        } catch let e as LocalizedError {
            status(e.errorDescription ?? "Archive creation failed.")
        } catch {
            status("Archive creation failed.")
        }
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
