import AppKit
import NiteSubmitCore

/// AppKit update window controller presenting software update alerts with Obsidian Palette B styling.
final class UpdateModalView: NSWindowController {
    private var item: AppcastItem?
    private var currentVersion: SemanticVersion?

    convenience init(item: AppcastItem, currentVersion: SemanticVersion) {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 320),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false
        )
        win.title = "Software Update — NITE Submit"
        win.appearance = NSAppearance(named: .darkAqua)
        win.center()

        self.init(window: win)
        self.item = item
        self.currentVersion = currentVersion

        setupUI(win: win, item: item, currentVersion: currentVersion)
    }

    private func setupUI(win: NSWindow, item: AppcastItem, currentVersion: SemanticVersion) {
        let view = NSView(frame: win.contentView!.bounds)
        view.wantsLayer = true
        view.layer?.backgroundColor = NiteSubmitUI.background.cgColor
        win.contentView = view

        let titleLabel = NSTextField(labelWithString: "A new version of NITE Submit is available!")
        titleLabel.font = .systemFont(ofSize: 14, weight: .bold)
        titleLabel.textColor = NiteSubmitUI.cyan

        let versionLabel = NSTextField(labelWithString: "NITE Submit \(item.versionString) is now available (you have \(currentVersion.description)).")
        versionLabel.font = .systemFont(ofSize: 11, weight: .medium)
        versionLabel.textColor = NiteSubmitUI.foreground

        let notesHeader = NSTextField(labelWithString: "Release notes")
        notesHeader.font = .systemFont(ofSize: 11, weight: .semibold)
        notesHeader.textColor = NiteSubmitUI.muted

        let notesBox = NSScrollView()
        notesBox.hasVerticalScroller = true
        notesBox.drawsBackground = false
        notesBox.translatesAutoresizingMaskIntoConstraints = false

        let textView = NSTextView()
        textView.isEditable = false
        textView.isSelectable = true
        textView.backgroundColor = NiteSubmitUI.surface
        textView.textColor = NiteSubmitUI.foreground
        textView.font = .systemFont(ofSize: 11)
        textView.string = item.releaseNotes.isEmpty ? "Performance improvements, university rule updates, and bug fixes." : item.releaseNotes
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: notesBox.contentSize.width, height: .greatestFiniteMagnitude)
        notesBox.documentView = textView

        let downloadBtn = NSButton(title: "Open Secure Download Page", target: self, action: #selector(downloadClicked))
        NiteSubmitUI.stylePrimaryButton(downloadBtn)

        let cancelBtn = NSButton(title: "Remind Me Later", target: self, action: #selector(cancelClicked))
        NiteSubmitUI.styleSecondaryButton(cancelBtn)

        let btnStack = NSStackView(views: [cancelBtn, downloadBtn])
        btnStack.orientation = .horizontal
        btnStack.spacing = 10
        btnStack.alignment = .centerY

        let stack = NSStackView(views: [titleLabel, versionLabel, notesHeader, notesBox, btnStack])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -16),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),

            notesBox.widthAnchor.constraint(equalTo: stack.widthAnchor),
            notesBox.heightAnchor.constraint(equalToConstant: 140),
            btnStack.trailingAnchor.constraint(equalTo: stack.trailingAnchor)
        ])
    }

    @objc private func downloadClicked() {
        guard let url = item?.downloadURL else { return }
        NSWorkspace.shared.open(url)
        window?.close()
    }

    @objc private func cancelClicked() {
        window?.close()
    }
}
