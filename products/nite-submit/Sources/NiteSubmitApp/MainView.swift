import AppKit
import NiteSubmitCore
import UniformTypeIdentifiers

/// One real, locally-loaded document in the queue rack.
struct DocumentItem {
    let name: String
    let kind: String
    let url: URL
    var statusText: String
    var isVerified: Bool
    /// Captured review state, so switching away and back preserves what the user already
    /// reviewed/edited/approved instead of re-detecting from scratch. Nil until the item has been
    /// selected at least once.
    var documentState: SubmitController.DocumentState? = nil
}

/// Top-down flipped NSView for smooth vertical scrolling in NSScrollView.
final class FlippedContentView: NSView {
    override var isFlipped: Bool { true }
}

/// Root view matching 100% of the UX features, card interactions, pipeline stepper, and findings rack from `SubmitPrepDemo.tsx`.
final class MainView: NSView, NSTextFieldDelegate {
    var controller: SubmitController?

    let dropZone = DropZoneView()
    let stepperView = PipelineStepperView()
    let privacyBadge = PrivacyBadgeView()

    // Document Queue Rack
    private var queueItems: [DocumentItem] = []
    private var selectedIndex: Int = 0
    private var queueButtons: [NSButton] = []

    // Findings & Inspection Rack
    private let inspectionTitle = NSTextField(labelWithString: "Detected details")
    private var fieldRows: [(field: MetadataField, led: StatusLEDView, text: NSTextField,
                             status: NSTextField, candidateButton: NSPopUpButton)] = []
    /// Hidden until a file is loaded (progressive disclosure): a brand-new user otherwise saw a
    /// dense wall of ~15 empty controls (9 field rows, every picker, the LCD box) before there
    /// was anything to act on. Toggled in refreshReviewState(), the same place that already knows
    /// whether a document is loaded.
    private var rowsContainer: NSStackView?
    private var detailsRows: NSStackView?
    private var bottomSection: NSStackView?
    private var settingsContainer: NSStackView?
    private var advancedActionsContainer: NSStackView?
    private var reviewRow: NSStackView?
    private var primaryActionRow: NSStackView?
    private var isShowingAllDetails = false
    private var isShowingSettings = false
    private var isShowingAdvancedActions = false
    private let detailsDisclosureButton = NSButton(title: "Show all", target: nil, action: nil)
    private let settingsDisclosureButton = NSButton(title: "Naming & document settings", target: nil, action: nil)
    private let actionsDisclosureButton = NSButton(title: "More export options", target: nil, action: nil)
    private let reviewSectionLabel = NSTextField(labelWithString: "2  REVIEW")
    private let exportSectionLabel = NSTextField(labelWithString: "3  CREATE")
    private let emptyStateLabel = NSTextField(labelWithString: "Add a file to check its details and create a clean submission copy.")

    // Naming Rule & Controls
    let templatePopup = NSPopUpButton()
    let profilePopup = NSPopUpButton()
    let importPresetButton = NSButton(title: "Import…", target: nil, action: nil)
    let exportPresetButton = NSButton(title: "Export…", target: nil, action: nil)
    let identityPolicyPopup = NSPopUpButton()
    let defaultStudentIdField = NSTextField()
    let clearStudentIdButton = NSButton(title: "Clear", target: nil, action: nil)
    let templateField = NSTextField()

    // LCD Output Box
    let lcdBox = LCDContainerView()
    let previewLabel = NSTextField(labelWithString: "")
    let explanationLabel = NSTextField(labelWithString: "")
    let candidatesLabel = NSTextField(labelWithString: "")

    // Bottom Action Bar & Disclaimer
    let reviewLed = StatusLEDView()
    let reviewLabel = NSTextField(labelWithString: "Review required")
    let statusLabel = NSTextField(labelWithString: "Submit creates a local copy. It never uploads or submits your work.")

    let approveButton = NSButton(title: "Approve details", target: nil, action: nil)
    let copyButton = NSButton(title: "Approve & Create Renamed Copy", target: nil, action: nil)
    let archiveButton = NSButton(title: "Approve & Create 7z Archive", target: nil, action: nil)
    let archiveFormatPopup = NSPopUpButton()
    let volumeSplitPopup = NSPopUpButton()
    let passwordField = NSSecureTextField()
    /// Off by default: archiving otherwise puts byte-identical copies of the originals into the
    /// archive, matching every other export path in this app. When checked, PDFs are losslessly
    /// optimized (smaller, same visible content, different bytes — see PDFOptimizer) before being
    /// added, and only the archive itself, never the source files, is affected.
    let optimizePDFCheckbox = NSButton(checkboxWithTitle: "Optimize PDFs (smaller, lossless)", target: nil, action: nil)
    let renameButton = NSButton(title: "Rename Original…", target: nil, action: nil)
    let undoButton = NSButton(title: "Undo Rename", target: nil, action: nil)
    let resetButton = NSButton(title: "Reset Session", target: nil, action: nil)
    let copyNameButton = NSButton(title: "Copy Filename", target: nil, action: nil)

    /// The most recently rendered, sanitized base filename (no extension), or nil if the
    /// current fields/template don't yet produce a valid preview. Written by `refreshPreview()`.
    /// This never touches the filesystem — it only backs the clipboard-copy action.
    private var lastRenderedBaseName: String?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }
    required init?(coder: NSCoder) { fatalError() }

    func setup() {
        wantsLayer = true
        appearance = NSAppearance(named: .aqua)
        layer?.backgroundColor = NiteSubmitUI.background.cgColor
        setAccessibilityLabel("Submit document preparation console")

        // --- 1. Main Scrollable Container for Fluid Resizing ---
        let scrollView = NSScrollView(frame: bounds)
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        addSubview(scrollView)

        let contentView = FlippedContentView()
        contentView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.documentView = contentView

        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: bottomAnchor),
            scrollView.leadingAnchor.constraint(equalTo: leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: trailingAnchor),

            contentView.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor),
            contentView.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            contentView.trailingAnchor.constraint(equalTo: scrollView.contentView.trailingAnchor),
            contentView.widthAnchor.constraint(equalTo: scrollView.contentView.widthAnchor),
        ])

        // --- 2. Editorial header ---
        let brandLabel = NSTextField(labelWithString: "N I T E   D S P")
        brandLabel.font = .systemFont(ofSize: 9, weight: .medium)
        brandLabel.textColor = NiteSubmitUI.mutedDim

        let headerTitle = NSTextField(labelWithString: "Make it submission-ready.")
        headerTitle.font = .systemFont(ofSize: 27, weight: .medium)
        headerTitle.textColor = NiteSubmitUI.foreground

        let headerSubtitle = NSTextField(labelWithString: "Check the details, fix the filename and create the file you will submit.")
        headerSubtitle.font = .systemFont(ofSize: 12)
        headerSubtitle.textColor = NiteSubmitUI.muted

        let headerRow = NSStackView(views: [brandLabel, headerTitle, headerSubtitle, privacyBadge])
        headerRow.orientation = .vertical
        headerRow.alignment = .leading
        headerRow.spacing = 6
        headerRow.translatesAutoresizingMaskIntoConstraints = false

        // --- 3. Process Pipeline Stepper Bar ---
        stepperView.activeStep = .input
        stepperView.translatesAutoresizingMaskIntoConstraints = false

        // --- 4. Drop Zone & Document Selection Rack ---
        let selectionTitle = NSTextField(labelWithString: "1  ADD")
        selectionTitle.font = .systemFont(ofSize: 10, weight: .semibold)
        selectionTitle.textColor = NiteSubmitUI.mutedDim

        dropZone.onDrop = { [weak self] urls in
            self?.handleFilesDropped(urls)
        }
        dropZone.translatesAutoresizingMaskIntoConstraints = false

        let queueStack = NSStackView()
        queueStack.orientation = .vertical
        queueStack.alignment = .width
        queueStack.spacing = 6
        queueStack.translatesAutoresizingMaskIntoConstraints = false

        // The queue rack starts empty and is only ever populated by real files (drag-and-drop,
        // Finder/"Open With", or launch arguments all funnel through handleFilesDropped). It must
        // never contain placeholder/sample rows — a real document's review screen must only ever
        // show that document's real detected data, never canned demo content.
        queueItems = []

        let documentSection = NSStackView(views: [selectionTitle, dropZone, queueStack])
        documentSection.orientation = .vertical
        documentSection.alignment = .leading
        documentSection.spacing = 8
        documentSection.translatesAutoresizingMaskIntoConstraints = false

        // --- 5. Detected Details & Metadata Inspection Rack ---
        inspectionTitle.font = .systemFont(ofSize: 17, weight: .semibold)
        inspectionTitle.textColor = NiteSubmitUI.foreground

        let fieldsSub = NSTextField(labelWithString: "Only details that need your attention are shown.")
        fieldsSub.font = .systemFont(ofSize: 10)
        fieldsSub.textColor = NiteSubmitUI.mutedDim

        let fieldsHeading = NSStackView(views: [inspectionTitle, fieldsSub])
        fieldsHeading.orientation = .vertical
        fieldsHeading.spacing = 2
        fieldsHeading.alignment = .leading

        NiteSubmitUI.styleSecondaryButton(detailsDisclosureButton)
        detailsDisclosureButton.target = self
        detailsDisclosureButton.action = #selector(toggleAllDetails)

        let fieldsHeader = NSStackView(views: [fieldsHeading, detailsDisclosureButton])
        fieldsHeader.orientation = .horizontal
        fieldsHeader.spacing = 12
        fieldsHeader.alignment = .centerY
        fieldsHeader.distribution = .equalSpacing

        let rows = NSStackView()
        rows.orientation = .vertical
        rows.alignment = .width
        rows.spacing = 5
        rows.translatesAutoresizingMaskIntoConstraints = false
        self.detailsRows = rows

        let rowsContainer = NSStackView(views: [fieldsHeader, rows])
        rowsContainer.orientation = .vertical
        rowsContainer.alignment = .leading
        rowsContainer.spacing = 6
        rowsContainer.translatesAutoresizingMaskIntoConstraints = false
        self.rowsContainer = rowsContainer

        for field in MetadataField.allCases {
            let led = StatusLEDView()
            led.translatesAutoresizingMaskIntoConstraints = false

            let label = NSTextField(labelWithString: field.displayName)
            label.font = .systemFont(ofSize: 11, weight: .medium)
            label.textColor = NiteSubmitUI.muted
            label.widthAnchor.constraint(equalToConstant: 105).isActive = true

            let text = NSTextField(string: "")
            NiteSubmitUI.styleInput(text)
            text.delegate = self
            text.widthAnchor.constraint(greaterThanOrEqualToConstant: 160).isActive = true
            text.setContentHuggingPriority(.defaultLow, for: .horizontal)

            let status = NSTextField(labelWithString: "—")
            status.font = .systemFont(ofSize: 10, weight: .semibold)
            status.widthAnchor.constraint(equalToConstant: 75).isActive = true

            let candidateButton = NSPopUpButton(frame: .zero, pullsDown: false)
            candidateButton.addItem(withTitle: "Use…")
            candidateButton.target = self
            candidateButton.action = #selector(selectCandidate(_:))
            candidateButton.isHidden = true
            candidateButton.widthAnchor.constraint(equalToConstant: 85).isActive = true
            candidateButton.identifier = NSUserInterfaceItemIdentifier(field.rawValue)

            let row = NSStackView(views: [led, label, text, status, candidateButton])
            row.orientation = .horizontal
            row.alignment = .centerY
            row.spacing = 6
            row.translatesAutoresizingMaskIntoConstraints = false
            rows.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: rows.widthAnchor).isActive = true
            fieldRows.append((field, led, text, status, candidateButton))
        }

        // --- 6. Naming Rule & Profile Selectors ---
        let identityLabel = NSTextField(labelWithString: "Saved student number")
        identityLabel.font = .systemFont(ofSize: 11, weight: .medium)
        identityLabel.textColor = NiteSubmitUI.muted
        identityLabel.widthAnchor.constraint(equalToConstant: 135).isActive = true

        defaultStudentIdField.placeholderString = "Used when a PDF has no number"
        NiteSubmitUI.styleInput(defaultStudentIdField)
        defaultStudentIdField.delegate = self
        defaultStudentIdField.widthAnchor.constraint(greaterThanOrEqualToConstant: 180).isActive = true

        clearStudentIdButton.bezelStyle = .rounded
        clearStudentIdButton.target = self
        clearStudentIdButton.action = #selector(clearSavedStudentId)

        let identityRow = NSStackView(views: [identityLabel, defaultStudentIdField, clearStudentIdButton])
        identityRow.orientation = .horizontal
        identityRow.spacing = 8

        let ruleLabel = NSTextField(labelWithString: "Naming rule")
        ruleLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        ruleLabel.textColor = NiteSubmitUI.cyan

        refreshTemplatePopup()
        NiteSubmitUI.stylePopup(templatePopup)
        templatePopup.target = self
        templatePopup.action = #selector(presetChanged)

        for profile in Presets.universityProfiles {
            profilePopup.addItem(withTitle: profile.displayName)
        }
        NiteSubmitUI.stylePopup(profilePopup)
        profilePopup.target = self
        profilePopup.action = #selector(profileChanged)

        templateField.placeholderString = "{student_id}_{project_title}"
        NiteSubmitUI.styleInput(templateField)
        templateField.delegate = self
        templateField.widthAnchor.constraint(greaterThanOrEqualToConstant: 180).isActive = true

        NiteSubmitUI.styleSecondaryButton(importPresetButton)
        importPresetButton.target = self
        importPresetButton.action = #selector(importPreset)

        NiteSubmitUI.styleSecondaryButton(exportPresetButton)
        exportPresetButton.target = self
        exportPresetButton.action = #selector(exportPreset)

        let ruleRow = NSStackView(views: [templatePopup, templateField, importPresetButton, exportPresetButton])
        ruleRow.orientation = .horizontal
        ruleRow.spacing = 8

        let profileLabel = NSTextField(labelWithString: "University profile")
        profileLabel.font = .systemFont(ofSize: 11, weight: .medium)
        profileLabel.textColor = NiteSubmitUI.muted
        profileLabel.widthAnchor.constraint(equalToConstant: 135).isActive = true

        let profileRow = NSStackView(views: [profileLabel, profilePopup])
        profileRow.orientation = .horizontal
        profileRow.spacing = 8

        let identityPolicyLabel = NSTextField(labelWithString: "Document identity")
        identityPolicyLabel.font = .systemFont(ofSize: 11, weight: .medium)
        identityPolicyLabel.textColor = NiteSubmitUI.muted
        identityPolicyLabel.widthAnchor.constraint(equalToConstant: 135).isActive = true

        for policy in DocumentIdentityPolicy.allCases {
            identityPolicyPopup.addItem(withTitle: Self.identityPolicyTitle(policy))
            identityPolicyPopup.lastItem?.representedObject = policy.rawValue
        }
        identityPolicyPopup.target = self
        identityPolicyPopup.action = #selector(identityPolicyChanged)
        NiteSubmitUI.stylePopup(identityPolicyPopup)

        let identityPolicyRow = NSStackView(views: [identityPolicyLabel, identityPolicyPopup])
        identityPolicyRow.orientation = .horizontal
        identityPolicyRow.spacing = 8

        // --- 7. Inset LCD Output Display Container (Module 02 Output Preview) ---
        lcdBox.translatesAutoresizingMaskIntoConstraints = false

        let lcdHeader = NSTextField(labelWithString: "PROPOSED FILENAME")
        lcdHeader.font = .systemFont(ofSize: 9, weight: .semibold)
        lcdHeader.textColor = NiteSubmitUI.mutedDim

        // Kept monospace deliberately: this is the one genuine technical readout in the app
        // (the exact generated filename) where showing precise characters matters.
        previewLabel.font = .monospacedSystemFont(ofSize: 12, weight: .bold)
        previewLabel.textColor = NiteSubmitUI.foreground

        explanationLabel.font = .systemFont(ofSize: 10)
        explanationLabel.textColor = NiteSubmitUI.muted
        explanationLabel.lineBreakMode = .byWordWrapping
        explanationLabel.maximumNumberOfLines = 2

        candidatesLabel.font = .systemFont(ofSize: 10)
        candidatesLabel.textColor = NiteSubmitUI.mutedDim
        candidatesLabel.lineBreakMode = .byWordWrapping
        candidatesLabel.maximumNumberOfLines = 2

        let lcdStack = NSStackView(views: [lcdHeader, previewLabel, explanationLabel])
        lcdStack.orientation = .vertical
        lcdStack.alignment = .leading
        lcdStack.spacing = 4
        lcdStack.translatesAutoresizingMaskIntoConstraints = false
        lcdBox.addSubview(lcdStack)

        NSLayoutConstraint.activate([
            lcdStack.topAnchor.constraint(equalTo: lcdBox.topAnchor, constant: 8),
            lcdStack.bottomAnchor.constraint(equalTo: lcdBox.bottomAnchor, constant: -8),
            lcdStack.leadingAnchor.constraint(equalTo: lcdBox.leadingAnchor, constant: 10),
            lcdStack.trailingAnchor.constraint(equalTo: lcdBox.trailingAnchor, constant: -10),
        ])

        // --- 8. Review and export ---
        reviewLabel.font = .systemFont(ofSize: 11, weight: .semibold)
        reviewLed.translatesAutoresizingMaskIntoConstraints = false

        let reviewLedStack = NSStackView(views: [reviewLed, reviewLabel])
        reviewLedStack.orientation = .horizontal
        reviewLedStack.spacing = 6
        reviewLedStack.alignment = .centerY

        approveButton.title = "Approve details"
        NiteSubmitUI.stylePrimaryButton(approveButton)
        approveButton.target = self
        approveButton.action = #selector(approveDetails)
        approveButton.setAccessibilityLabel("Approve details")

        let reviewRow = NSStackView(views: [reviewLedStack, approveButton])
        reviewRow.orientation = .horizontal
        reviewRow.spacing = 12
        reviewRow.distribution = .equalSpacing
        self.reviewRow = reviewRow

        statusLabel.textColor = NiteSubmitUI.muted
        statusLabel.font = .systemFont(ofSize: 10)
        statusLabel.lineBreakMode = .byWordWrapping
        statusLabel.maximumNumberOfLines = 2

        NiteSubmitUI.stylePrimaryButton(copyButton)
        copyButton.title = "Create submission"
        copyButton.setAccessibilityLabel("Approve & Create Renamed Copy")
        copyButton.target = self
        copyButton.action = #selector(doCopy)
        copyButton.keyEquivalent = "\r"

        for fmt in ArchiveFormat.allCases {
            archiveFormatPopup.addItem(withTitle: fmt.displayName)
        }
        NiteSubmitUI.stylePopup(archiveFormatPopup)

        for opt in VolumeSplitOption.allCases {
            volumeSplitPopup.addItem(withTitle: opt.displayName)
        }
        NiteSubmitUI.stylePopup(volumeSplitPopup)

        passwordField.placeholderString = "Optional AES-256 Password"
        NiteSubmitUI.styleInput(passwordField)
        passwordField.widthAnchor.constraint(equalToConstant: 150).isActive = true

        optimizePDFCheckbox.state = .off
        optimizePDFCheckbox.toolTip = "Losslessly shrinks PDFs before adding them to the archive — same visible content, smaller file. Your original file is never modified; this only changes what goes into the archive."
        optimizePDFCheckbox.font = .systemFont(ofSize: 11)
        optimizePDFCheckbox.contentTintColor = NiteSubmitUI.cyan
        optimizePDFCheckbox.wantsLayer = true

        NiteSubmitUI.stylePrimaryButton(archiveButton)
        archiveButton.target = self
        archiveButton.action = #selector(doArchive)

        NiteSubmitUI.styleSecondaryButton(renameButton)
        renameButton.target = self
        renameButton.action = #selector(doRename)

        NiteSubmitUI.styleSecondaryButton(undoButton)
        undoButton.target = self
        undoButton.action = #selector(doUndo)

        NiteSubmitUI.styleSecondaryButton(resetButton)
        resetButton.target = self
        resetButton.action = #selector(resetSession)

        NiteSubmitUI.styleSecondaryButton(copyNameButton)
        copyNameButton.target = self
        copyNameButton.action = #selector(copyFilenameOnly)
        copyNameButton.toolTip = "Copy the previewed filename to the clipboard. Never creates or renames a file."

        undoButton.isEnabled = false
        copyButton.isEnabled = false
        archiveButton.isEnabled = false
        renameButton.isEnabled = false
        copyNameButton.isEnabled = false

        let primaryActions = NSStackView(views: [copyButton])
        primaryActions.orientation = .horizontal
        primaryActions.spacing = 8
        primaryActions.alignment = .centerY
        self.primaryActionRow = primaryActions

        let advancedActions = NSStackView(views: [archiveButton, renameButton, archiveFormatPopup, volumeSplitPopup, passwordField, optimizePDFCheckbox, copyNameButton, undoButton, resetButton])
        advancedActions.orientation = .vertical
        advancedActions.alignment = .leading
        advancedActions.spacing = 7
        advancedActions.translatesAutoresizingMaskIntoConstraints = false
        advancedActions.isHidden = true
        self.advancedActionsContainer = advancedActions

        NiteSubmitUI.styleSecondaryButton(actionsDisclosureButton)
        actionsDisclosureButton.target = self
        actionsDisclosureButton.action = #selector(toggleAdvancedActions)

        let settings = NSStackView(views: [identityRow, profileRow, identityPolicyRow, ruleLabel, ruleRow])
        settings.orientation = .vertical
        settings.alignment = .leading
        settings.spacing = 8
        settings.isHidden = true
        self.settingsContainer = settings

        NiteSubmitUI.styleSecondaryButton(settingsDisclosureButton)
        settingsDisclosureButton.target = self
        settingsDisclosureButton.action = #selector(toggleSettings)

        reviewSectionLabel.font = .systemFont(ofSize: 10, weight: .semibold)
        reviewSectionLabel.textColor = NiteSubmitUI.mutedDim

        exportSectionLabel.font = .systemFont(ofSize: 10, weight: .semibold)
        exportSectionLabel.textColor = NiteSubmitUI.mutedDim

        let bottom = NSStackView(views: [settingsDisclosureButton, settings, lcdBox, reviewSectionLabel, reviewRow, exportSectionLabel, primaryActions, actionsDisclosureButton, advancedActions, statusLabel])
        bottom.orientation = .vertical
        bottom.alignment = .leading
        bottom.spacing = 10
        bottom.translatesAutoresizingMaskIntoConstraints = false
        self.bottomSection = bottom

        emptyStateLabel.font = .systemFont(ofSize: 12, weight: .regular)
        emptyStateLabel.textColor = NiteSubmitUI.mutedDim
        emptyStateLabel.translatesAutoresizingMaskIntoConstraints = false

        // Main Vertical Stack inside Content View
        let mainStack = NSStackView(views: [headerRow, documentSection, emptyStateLabel, rowsContainer, bottom])
        mainStack.orientation = .vertical
        mainStack.alignment = .leading
        mainStack.spacing = 18
        mainStack.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(mainStack)

        // Progressive disclosure: nothing to review yet on a fresh launch, so start with just the
        // drop zone and a plain-language prompt rather than ~15 empty controls all at once.
        rowsContainer.isHidden = true
        bottom.isHidden = true

        NSLayoutConstraint.activate([
            mainStack.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 28),
            mainStack.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -28),
            mainStack.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 30),
            mainStack.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -30),

            headerRow.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            documentSection.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            emptyStateLabel.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            queueStack.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            dropZone.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            dropZone.heightAnchor.constraint(equalToConstant: 116),
            rowsContainer.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            rows.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            bottom.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            lcdBox.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            fieldsHeader.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
            reviewRow.widthAnchor.constraint(equalTo: mainStack.widthAnchor),
        ])

        let appSettings = AppSettings.load()
        if let idx = Presets.builtIn.firstIndex(where: { $0.id == appSettings.presetId }) {
            templatePopup.selectItem(at: idx)
        }
        if let idx = Presets.universityProfiles.firstIndex(where: { $0.id == appSettings.universityPresetId }) {
            profilePopup.selectItem(at: idx)
        }
        if let idx = DocumentIdentityPolicy.allCases.firstIndex(of: appSettings.documentIdentityPolicy) {
            identityPolicyPopup.selectItem(at: idx)
        }
        defaultStudentIdField.stringValue = appSettings.defaultStudentId
        templateField.stringValue = appSettings.template

        // Select first document by default
        updateSelectionUI(index: 0)
    }

    // MARK: - Queue Helpers & Interaction Callbacks

    private func createQueueButton(for item: DocumentItem, index: Int) -> NSButton {
        let button = NSButton(title: "", target: self, action: #selector(queueItemClicked(_:)))
        button.tag = index
        button.setButtonType(.momentaryPushIn)
        button.bezelStyle = .inline
        button.wantsLayer = true
        // The button's title is empty (its content is custom-drawn subviews via
        // updateQueueButtonAppearance), so without an explicit accessibility label VoiceOver and
        // UI automation both see an anonymous, indistinguishable control here.
        button.setAccessibilityLabel("\(item.name), \(item.statusText)")

        updateQueueButtonAppearance(button, item: item, isSelected: index == selectedIndex)
        button.heightAnchor.constraint(equalToConstant: 42).isActive = true
        return button
    }

    private func updateQueueButtonAppearance(_ button: NSButton, item: DocumentItem, isSelected: Bool) {
        button.setAccessibilityLabel("\(item.name), \(item.statusText)")
        let container = NSStackView()
        container.orientation = .horizontal
        container.alignment = .centerY
        container.distribution = .equalSpacing

        let ext = (item.name as NSString).pathExtension.uppercased()
        let fileTag = ext.isEmpty ? "[FILE]" : "[\(ext)]"
        let fileIcon = NSTextField(labelWithString: fileTag)
        fileIcon.font = .systemFont(ofSize: 9, weight: .bold)
        fileIcon.textColor = isSelected ? NiteSubmitUI.cyan : NiteSubmitUI.mutedDim

        let fileNameLabel = NSTextField(labelWithString: item.name)
        fileNameLabel.font = .systemFont(ofSize: 12, weight: .medium)
        fileNameLabel.textColor = isSelected ? NiteSubmitUI.cyan : NiteSubmitUI.foreground

        let fileKindLabel = NSTextField(labelWithString: item.kind)
        fileKindLabel.font = .systemFont(ofSize: 10)
        fileKindLabel.textColor = NiteSubmitUI.mutedDim

        let nameStack = NSStackView(views: [fileNameLabel, fileKindLabel])
        nameStack.orientation = .vertical
        nameStack.alignment = .leading
        nameStack.spacing = 1

        let leftPart = NSStackView(views: [fileIcon, nameStack])
        leftPart.orientation = .horizontal
        leftPart.spacing = 8
        leftPart.alignment = .centerY

        let statusBadge = NSTextField(labelWithString: item.statusText)
        statusBadge.font = .systemFont(ofSize: 9, weight: .bold)
        statusBadge.textColor = isSelected ? NiteSubmitUI.cyan : NiteSubmitUI.mutedDim

        button.subviews.forEach { $0.removeFromSuperview() }
        button.addSubview(container)
        container.addArrangedSubview(leftPart)
        container.addArrangedSubview(statusBadge)
        container.translatesAutoresizingMaskIntoConstraints = false

        NSLayoutConstraint.activate([
            container.topAnchor.constraint(equalTo: button.topAnchor, constant: 4),
            container.bottomAnchor.constraint(equalTo: button.bottomAnchor, constant: -4),
            container.leadingAnchor.constraint(equalTo: button.leadingAnchor, constant: 10),
            container.trailingAnchor.constraint(equalTo: button.trailingAnchor, constant: -10),
        ])

        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.20
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            button.layer?.backgroundColor = isSelected ? NiteSubmitUI.surfaceRaised.cgColor : NiteSubmitUI.surface.cgColor
            button.layer?.cornerRadius = 6
            button.layer?.borderWidth = 1
            button.layer?.borderColor = isSelected ? NiteSubmitUI.cyan.withAlphaComponent(0.6).cgColor : NiteSubmitUI.border.cgColor
        }
    }

    private func updateSelectionUI(index: Int) {
        guard index >= 0 && index < queueItems.count else { return }

        // Preserve the outgoing item's real review state (metadata edits, approval, etc.) so
        // switching back to it later doesn't lose work or re-run detection from scratch. Guarded
        // on index != selectedIndex and hasLoadedDocument so this never fires for the first item
        // ever added to an empty queue — selectedIndex's initial value (0) otherwise coincides
        // with that very first item's own index, wrongly "capturing" the controller's blank
        // pre-load state and restoring that blank state instead of ever calling loadPDF.
        if index != selectedIndex, selectedIndex >= 0, selectedIndex < queueItems.count,
           let controller, controller.hasLoadedDocument {
            queueItems[selectedIndex].documentState = controller.captureState()
        }

        selectedIndex = index
        stepperView.activeStep = .analysis

        for (idx, btn) in queueButtons.enumerated() {
            updateQueueButtonAppearance(btn, item: queueItems[idx], isSelected: idx == selectedIndex)
        }

        let item = queueItems[selectedIndex]
        inspectionTitle.stringValue = "Detected details — \(item.name)"

        if let state = item.documentState {
            controller?.restore(state)
        } else {
            controller?.loadPDF(at: item.url)
        }

        stepperView.activeStep = .recommendation
    }

    /// Reflects the currently-selected real document's actual review state (not a guess) onto
    /// its queue row — "REVIEW REQUIRED" / blocked / "APPROVED" — so the rack never shows fake
    /// status for a file that has real, per-item detection behind it. Called after every state
    /// change (`refreshReviewState`).
    private func syncSelectedQueueItemStatus() {
        guard selectedIndex >= 0, selectedIndex < queueItems.count, let controller else { return }
        let approved = controller.reviewApproved
        queueItems[selectedIndex].isVerified = approved
        queueItems[selectedIndex].statusText = approved
            ? "Approved"
            : (controller.reviewBlockingReason() != nil ? "Check file" : "Review required")
        if selectedIndex < queueButtons.count {
            updateQueueButtonAppearance(queueButtons[selectedIndex], item: queueItems[selectedIndex],
                                        isSelected: true)
        }
    }

    @objc func queueItemClicked(_ sender: NSButton) {
        updateSelectionUI(index: sender.tag)
    }

    /// Adds one or more dropped/picked PDFs as independent queue rows, each keeping its own real
    /// detection/review state (see `DocumentItem.documentState`). Selects the last one added.
    /// Approval always still happens per-item via the shared approve button acting on whichever
    /// row is selected — dropping many files never approves or writes anything by itself.
    ///
    /// This is also the entry point for files opened via Finder/"Open With"/launch arguments
    /// (see `AppDelegate.openPDF`), not just drag-and-drop — every way of opening a document must
    /// go through here so the visible queue rack and review fields always reflect the real file
    /// being acted on, never a stale or placeholder selection.
    func handleFilesDropped(_ urls: [URL]) {
        guard !urls.isEmpty else { return }
        var lastIndex = selectedIndex
        for url in urls {
            let name = url.lastPathComponent
            let kind = "\(url.pathExtension.uppercased()) document · Local"
            let newItem = DocumentItem(name: name, kind: kind, url: url, statusText: "Review required",
                                       isVerified: false)

            queueItems.append(newItem)
            let index = queueItems.count - 1

            let btn = createQueueButton(for: newItem, index: index)
            queueButtons.append(btn)

            if let documentSection = dropZone.superview as? NSStackView,
               let queueStack = documentSection.arrangedSubviews.compactMap({ $0 as? NSStackView }).last {
                queueStack.addArrangedSubview(btn)
                btn.widthAnchor.constraint(equalTo: queueStack.widthAnchor).isActive = true
            }
            lastIndex = index
        }
        updateSelectionUI(index: lastIndex)
    }

    @objc func resetSession() {
        controller?.reset()
        stepperView.activeStep = .input
        statusLabel.stringValue = "Session reset — Submit helps you prepare safely. Submit does not submit automatically."
        updateSelectionUI(index: 0)
        refreshFields()
    }

    @objc private func toggleAllDetails() {
        isShowingAllDetails.toggle()
        detailsDisclosureButton.title = isShowingAllDetails
            ? "Show issues"
            : "Show all"
        refreshFields()
    }

    @objc private func toggleSettings() {
        isShowingSettings.toggle()
        settingsContainer?.isHidden = !isShowingSettings
        settingsDisclosureButton.title = isShowingSettings
            ? "Hide naming & document settings"
            : "Naming & document settings"
    }

    @objc private func toggleAdvancedActions() {
        isShowingAdvancedActions.toggle()
        advancedActionsContainer?.isHidden = !isShowingAdvancedActions
        actionsDisclosureButton.title = isShowingAdvancedActions
            ? "Hide export options"
            : "More export options"
    }

    // MARK: - Editing Callbacks

    func controlTextDidChange(_ obj: Notification) {
        guard let field = obj.object as? NSTextField else { return }
        if field === defaultStudentIdField {
            controller?.setDefaultStudentId(field.stringValue)
        } else if field === templateField {
            controller?.settings.applyCustomTemplate(field.stringValue)
            controller?.settings.save()
            controller?.invalidateReview()
        } else if let row = fieldRows.first(where: { $0.text === field }) {
            controller?.setManualValue(field.stringValue, for: row.field)
        }
        refreshFields()
    }

    func controlTextDidEndEditing(_ obj: Notification) {
        controlTextDidChange(obj)
    }

    func promptForDefaultStudentIdIfNeeded() {
        guard let controller,
              controller.settings.defaultStudentId.isEmpty,
              !controller.settings.hasPromptedForDefaultStudentId else { return }
        controller.settings.hasPromptedForDefaultStudentId = true
        controller.settings.save()
        let alert = NSAlert()
        alert.messageText = "Save your student number?"
        alert.informativeText = "Submit can reuse it when a PDF does not contain a student number. It stays on this Mac and can be changed below."
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        field.placeholderString = "e.g. 12345678"
        alert.accessoryView = field
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Not now")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        controller.setDefaultStudentId(field.stringValue)
        defaultStudentIdField.stringValue = controller.settings.defaultStudentId
        refreshFields()
    }

    @objc func clearSavedStudentId() {
        controller?.setDefaultStudentId("")
        defaultStudentIdField.stringValue = ""
        statusLabel.stringValue = "Saved student number cleared from this Mac."
        refreshFields()
    }

    /// Built-in presets plus any imported custom presets, in the order shown in `templatePopup`.
    /// Imported presets always carry `.userCreated` status (see `AppSettings.addImportedPreset`) —
    /// they are labelled as such in the popup and can never claim `.verified`.
    func combinedTemplatePresets() -> [NamingPreset] {
        Presets.builtIn + (controller?.settings.customPresets ?? [])
    }

    /// Rebuilds `templatePopup` from the built-in presets plus any imported custom presets.
    /// Imported entries are suffixed "(Custom)" so their provenance is always visible.
    func refreshTemplatePopup() {
        let selectedId = controller?.settings.presetId
        templatePopup.removeAllItems()
        for p in Presets.builtIn { templatePopup.addItem(withTitle: p.displayName) }
        let custom = controller?.settings.customPresets ?? []
        for p in custom { templatePopup.addItem(withTitle: "\(p.displayName) (Custom)") }
        if let selectedId, let idx = combinedTemplatePresets().firstIndex(where: { $0.id == selectedId }) {
            templatePopup.selectItem(at: idx)
        }
    }

    @objc func presetChanged() {
        let presets = combinedTemplatePresets()
        let idx = templatePopup.indexOfSelectedItem
        guard idx >= 0, idx < presets.count else { return }
        templateField.stringValue = presets[idx].template
        controller?.settings.presetId = presets[idx].id
        controller?.settings.template = presets[idx].template
        controller?.settings.save()
        refreshFields()
    }

    /// Exports the currently selected naming preset to a `.submitrule.json` file so it can be
    /// shared (e.g. a tutor distributing a department's naming rule to a cohort). Exports only
    /// the preset's shape — id, name, template, required fields — never document contents.
    @objc func exportPreset() {
        let presets = combinedTemplatePresets()
        let idx = templatePopup.indexOfSelectedItem
        guard idx >= 0, idx < presets.count else { return }
        let preset = presets[idx]

        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(preset.displayName).submitrule.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }

        do {
            let data = try JSONEncoder().encode(preset)
            try data.write(to: url, options: .atomic)
            statusLabel.stringValue = "Exported naming rule to \(url.lastPathComponent)."
        } catch {
            statusLabel.stringValue = "Could not export the naming rule: \(error.localizedDescription)"
        }
    }

    /// Imports a `.submitrule.json` naming preset. Imported status is always clamped to
    /// `.userCreated` regardless of what the file claims — an imported preset can never present
    /// as officially `.verified`. This keeps the "no official rule database" promise honest.
    @objc func importPreset() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK, let url = panel.url else { return }

        do {
            let data = try Data(contentsOf: url)
            let preset = try JSONDecoder().decode(NamingPreset.self, from: data)
            controller?.settings.addImportedPreset(preset)
            controller?.settings.save()
            refreshTemplatePopup()
            statusLabel.stringValue = "Imported \"\(preset.displayName)\" as a user-created naming rule (not verified)."
        } catch {
            statusLabel.stringValue = "Could not import that file as a naming rule: \(error.localizedDescription)"
        }
    }

    @objc func profileChanged() {
        let idx = profilePopup.indexOfSelectedItem
        guard idx >= 0, idx < Presets.universityProfiles.count else { return }
        let profile = Presets.universityProfiles[idx]
        templateField.stringValue = profile.template
        controller?.settings.universityPresetId = profile.id
        controller?.settings.template = profile.template
        controller?.settings.save()
        refreshFields()
    }

    @objc func identityPolicyChanged() {
        let idx = identityPolicyPopup.indexOfSelectedItem
        guard idx >= 0, idx < DocumentIdentityPolicy.allCases.count else { return }
        controller?.setDocumentIdentityPolicy(DocumentIdentityPolicy.allCases[idx])
        refreshFields()
    }

    static func identityPolicyTitle(_ policy: DocumentIdentityPolicy) -> String {
        switch policy {
        case .noRule: return "No rule (check brief)"
        case .nameRequired: return "Name required in document"
        case .nameProhibited: return "Anonymous — name prohibited"
        }
    }

    func refreshPreview() {
        guard let c = controller, c.sourceURL != nil else { return }
        defer { refreshReviewState() }
        let documentNote: String = {
            guard c.documentClassification.kind == .guidanceTemplate else { return "" }
            return " Warning: this PDF looks like university guidance or a template, not a student submission. Verify it before renaming."
        }()
        let identityNote = c.documentIdentityCheck.evidence == "No document identity rule selected"
            ? ""
            : " Document identity: \(c.documentIdentityCheck.evidence)."
        let tpl = templateField.stringValue
        if let p = TemplateEngine.validate(tpl).first {
            previewLabel.stringValue = "⚠︎ \(p)"
            previewLabel.textColor = NiteSubmitUI.warning
            explanationLabel.stringValue = "Why: fix the naming rule before reviewing the document.\(identityNote)\(documentNote)"
            lastRenderedBaseName = nil
            copyNameButton.isEnabled = false
            return
        }
        if c.settings.universityPresetId == "anonymous_candidate" {
            let nameFields = Set(["first_name", "last_name", "full_name"])
            if !nameFields.isDisjoint(with: Set(tpl.variables())) {
                previewLabel.stringValue = "⚠︎ Anonymous profile cannot include a student name."
                previewLabel.textColor = NiteSubmitUI.error
                explanationLabel.stringValue = "Why: anonymous submissions must not contain personal names.\(identityNote)\(documentNote)"
                lastRenderedBaseName = nil
                copyNameButton.isEnabled = false
                return
            }
        }
        if let identityReason = c.documentIdentityCheck.blockingReason {
            previewLabel.stringValue = "⚠︎ \(identityReason)"
            previewLabel.textColor = NiteSubmitUI.error
            explanationLabel.stringValue = "Why: resolve the document identity policy before approving.\(documentNote)"
            lastRenderedBaseName = nil
            copyNameButton.isEnabled = false
            return
        }
        let values = c.currentValues()
        if let m = TemplateEngine.missingRequiredFields(tpl, values: values).first {
            previewLabel.stringValue = "⚠︎ \(m)"
            previewLabel.textColor = NiteSubmitUI.warning
            explanationLabel.stringValue = "Why: the selected naming rule is missing a required field.\(identityNote)\(documentNote)"
            lastRenderedBaseName = nil
            copyNameButton.isEnabled = false
            return
        }
        let base = c.originalBaseName ?? "assignment"
        if let rendered = TemplateEngine.render(template: tpl, values: values, originalName: base) {
            previewLabel.stringValue = rendered + ".pdf"
            previewLabel.textColor = NiteSubmitUI.foreground
            lastRenderedBaseName = rendered
            copyNameButton.isEnabled = true
            stepperView.activeStep = .recommendation
            let needsReview = MetadataField.allCases.contains {
                let detection = c.metadata.detection(for: $0)
                return !detection.isMissing && detection.confidence < .high
            }
            explanationLabel.stringValue = needsReview
                ? "Review the highlighted details, then approve this filename." + identityNote + documentNote
                : "Required details are present. Approve when the filename looks right." + identityNote + documentNote
        } else {
            previewLabel.stringValue = "—"
            explanationLabel.stringValue = "Why: a safe filename could not be built from the current fields.\(identityNote)\(documentNote)"
            lastRenderedBaseName = nil
            copyNameButton.isEnabled = false
        }
    }

    /// Copies the currently previewed filename to the clipboard. This never creates, renames, or
    /// touches any file on disk — it is purely a "copy the name I'd get" convenience.
    @objc func copyFilenameOnly() {
        guard let base = lastRenderedBaseName else { return }
        let name = base + ".pdf"
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(name, forType: .string)

        if let reason = FilenameSanitizer.invalidBaseNameReason(base) {
            explanationLabel.stringValue = "Copied \"\(name)\" — but ⚠︎ \(reason). Submit would reject this exact name on write; the saved file may differ."
        } else {
            explanationLabel.stringValue = "Copied \"\(name)\" to the clipboard. This is the base name only — a collision may add a numeric suffix when actually saved."
        }
    }

    func refreshFields() {
        guard let c = controller else { return }
        let templateVariables = Set(templateField.stringValue.variables())
        var attentionCount = 0
        for row in fieldRows {
            let d = c.metadata.detection(for: row.field)
            row.text.stringValue = d.value ?? ""
            let required = fieldIsRequired(row.field, variables: templateVariables)
            let needsAttention = d.confidence == .medium || d.confidence == .low ||
                (d.confidence == .missing && required)
            if needsAttention { attentionCount += 1 }
            row.text.superview?.isHidden = !isShowingAllDetails && !needsAttention
            switch d.confidence {
            case .high:
                row.led.state = .green
                row.status.stringValue = "Verified"
                row.status.textColor = NiteSubmitUI.success
                row.text.placeholderString = nil
            case .medium, .low:
                row.led.state = .amber
                row.status.stringValue = "Check"
                row.status.textColor = NiteSubmitUI.warning
                row.text.placeholderString = nil
            case .missing:
                if required {
                    row.led.state = .red
                    row.status.stringValue = "Required"
                    row.status.textColor = NiteSubmitUI.error
                    row.text.placeholderString = "Enter \(row.field.displayName.lowercased())"
                } else {
                    row.led.state = .off
                    row.status.stringValue = "Optional"
                    row.status.textColor = NiteSubmitUI.mutedDim
                    row.text.placeholderString = nil
                }
            }
            var tooltip = d.source ?? "No evidence found"
            if !d.candidates.isEmpty {
                tooltip += "\nAlternatives: " + d.candidates.joined(separator: " · ")
            }
            row.text.toolTip = tooltip
            row.candidateButton.removeAllItems()
            row.candidateButton.addItem(withTitle: "Use…")
            for candidate in d.candidates {
                row.candidateButton.addItem(withTitle: candidate)
            }
            row.candidateButton.isHidden = d.candidates.isEmpty
            row.candidateButton.toolTip = d.candidates.isEmpty
                ? nil : "Choose a detected alternative, then review the filename again."
        }
        let alternatives = MetadataField.allCases.compactMap { field -> String? in
            let d = c.metadata.detection(for: field)
            guard !d.candidates.isEmpty else { return nil }
            return "\(field.displayName): \(d.candidates.joined(separator: " · "))"
        }
        candidatesLabel.stringValue = alternatives.isEmpty
            ? "Hover over fields for evidence. Optional fields are not needed unless the naming rule uses them."
            : "Choose an alternative from its field menu or edit the field manually:\n" +
                alternatives.joined(separator: "\n")
        if let name = c.sourceURL?.lastPathComponent {
            inspectionTitle.stringValue = attentionCount == 0
                ? "Details look complete"
                : "\(attentionCount) detail\(attentionCount == 1 ? "" : "s") to check"
            inspectionTitle.toolTip = name
        }
        refreshPreview()
    }

    @objc func selectCandidate(_ sender: NSPopUpButton) {
        guard let rawField = sender.identifier?.rawValue,
              let field = MetadataField(rawValue: rawField),
              sender.indexOfSelectedItem > 0,
              let selected = sender.titleOfSelectedItem else { return }
        controller?.setManualValue(selected, for: field)
        sender.selectItem(at: 0)
        refreshFields()
    }

    func fieldIsRequired(_ field: MetadataField, variables: Set<String>) -> Bool {
        switch field {
        case .studentName:
            return variables.contains("first_name") || variables.contains("last_name") ||
                variables.contains("full_name")
        case .studentId: return variables.contains("student_id")
        case .candidateNumber: return variables.contains("candidate_number")
        case .assignmentCode: return variables.contains("assignment_code")
        case .groupId: return variables.contains("group_id")
        case .projectTitle: return variables.contains("project_title")
        case .moduleCode: return variables.contains("module_code")
        case .moduleTitle: return variables.contains("module_title")
        case .university: return variables.contains("university")
        }
    }

    func refreshReviewState() {
        guard let c = controller else {
            reviewLed.state = .off
            approveButton.isEnabled = false
            copyButton.isEnabled = false
            renameButton.isEnabled = false
            return
        }
        let hasDocument = c.sourceURL != nil
        rowsContainer?.isHidden = !hasDocument
        bottomSection?.isHidden = !hasDocument
        emptyStateLabel.isHidden = hasDocument

        let blockingReason = c.reviewBlockingReason()
        if c.sourceURL == nil {
            reviewLed.state = .off
            reviewLabel.stringValue = "Load a PDF to begin"
            reviewLabel.textColor = NiteSubmitUI.mutedDim
        } else if c.reviewApproved {
            reviewLed.state = .green
            reviewLabel.stringValue = "Details verified & approved"
            reviewLabel.textColor = NiteSubmitUI.success
            stepperView.activeStep = .action
        } else if blockingReason != nil {
            reviewLed.state = .red
            reviewLabel.stringValue = "Resolve filename warning"
            reviewLabel.textColor = NiteSubmitUI.error
        } else {
            reviewLed.state = .amber
            reviewLabel.stringValue = "Review required before copy"
            reviewLabel.textColor = NiteSubmitUI.warning
        }
        approveButton.title = "Approve details"
        let safeToApprove = c.sourceURL != nil && blockingReason == nil
        approveButton.isEnabled = safeToApprove && !c.reviewApproved
        copyButton.isEnabled = c.reviewApproved && safeToApprove
        archiveButton.isEnabled = c.reviewApproved && safeToApprove
        renameButton.isEnabled = c.reviewApproved && safeToApprove
        reviewRow?.isHidden = c.reviewApproved || !hasDocument
        reviewSectionLabel.isHidden = c.reviewApproved || !hasDocument
        primaryActionRow?.isHidden = !c.reviewApproved || !hasDocument
        exportSectionLabel.isHidden = !c.reviewApproved || !hasDocument
        actionsDisclosureButton.isHidden = !c.reviewApproved || !hasDocument
        advancedActionsContainer?.isHidden = !c.reviewApproved || !hasDocument || !isShowingAdvancedActions
        syncSelectedQueueItemStatus()
    }

    // MARK: - Actions

    @objc func approveDetails() {
        guard let c = controller else { return }
        if c.approveReview() {
            statusLabel.stringValue = "Details approved — choose a file action below."
        } else {
            statusLabel.stringValue = c.reviewBlockingReason() ?? "Complete the required fields first."
        }
        refreshFields()
    }

    @objc func doCopy() {
        controller?.performOperation(.createCopy) { self.statusLabel.stringValue = $0 }
    }

    @objc func doArchive() {
        let realSources = queueItems.map { $0.url }
        let sources = realSources.isEmpty ? [controller?.sourceURL].compactMap { $0 } : realSources
        let idx = archiveFormatPopup.indexOfSelectedItem
        let format = (idx >= 0 && idx < ArchiveFormat.allCases.count) ? ArchiveFormat.allCases[idx] : .sevenZip

        let splitIdx = volumeSplitPopup.indexOfSelectedItem
        let volumeSplit = (splitIdx >= 0 && splitIdx < VolumeSplitOption.allCases.count) ? VolumeSplitOption.allCases[splitIdx] : .singleFile

        let pass = passwordField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let password = pass.isEmpty ? nil : pass

        guard optimizePDFCheckbox.state == .on else {
            controller?.performArchiveOperation(sources: sources, format: format, level: .normal, password: password, volumeSplit: volumeSplit) { self.statusLabel.stringValue = $0 }
            return
        }

        // Optimize PDFs into a scratch staging area first — the originals in `sources` are never
        // touched, only what goes into the archive changes. Non-PDF sources, and any PDF that
        // fails to optimize for whatever reason, pass through as their original file untouched
        // rather than blocking the whole archive over one file.
        let stagingDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try? FileManager.default.createDirectory(at: stagingDir, withIntermediateDirectories: true)
        var optimizedCount = 0
        var archiveSources: [URL] = []
        for source in sources {
            guard source.pathExtension.lowercased() == "pdf" else {
                archiveSources.append(source)
                continue
            }
            let staged = stagingDir.appendingPathComponent(source.lastPathComponent)
            if (try? PDFOptimizer().optimize(source: source, destination: staged)) != nil {
                archiveSources.append(staged)
                optimizedCount += 1
            } else {
                archiveSources.append(source)
            }
        }

        controller?.performArchiveOperation(sources: archiveSources, format: format, level: .normal, password: password, volumeSplit: volumeSplit) { [stagingDir] message in
            let suffix = optimizedCount > 0 ? " (\(optimizedCount) PDF\(optimizedCount == 1 ? "" : "s") optimized)" : ""
            self.statusLabel.stringValue = message + suffix
            try? FileManager.default.removeItem(at: stagingDir)
        }
    }

    @objc func doRename() {
        let alert = NSAlert()
        alert.messageText = "Rename the original file?"
        alert.informativeText = "Only the name changes — the content is untouched and can be undone."
        alert.addButton(withTitle: "Rename")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            controller?.performOperation(.renameOriginal) { self.statusLabel.stringValue = $0 }
        }
    }

    @objc func doUndo() {
        controller?.performUndo { self.statusLabel.stringValue = $0 }
    }
}
