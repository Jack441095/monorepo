import AppKit
import NiteSubmitCore

final class LicenseView: NSView {
    private let keyField = NSTextField()
    private let statusLabel = NSTextField(labelWithString: "")
    var onActivated: (() -> Void)?

    override init(frame: NSRect) {
        super.init(frame: frame)
        setupUI()
    }

    required init?(coder: NSCoder) { nil }

    private func setupUI() {
        let container = NSStackView()
        container.orientation = .vertical
        container.alignment = .centerX
        container.spacing = 16
        container.translatesAutoresizingMaskIntoConstraints = false
        addSubview(container)
        NSLayoutConstraint.activate([
            container.centerXAnchor.constraint(equalTo: centerXAnchor),
            container.centerYAnchor.constraint(equalTo: centerYAnchor),
            container.widthAnchor.constraint(lessThanOrEqualToConstant: 440),
            container.leadingAnchor.constraint(greaterThanOrEqualTo: leadingAnchor, constant: 24),
        ])

        let icon = NSTextField(labelWithString: "S")
        icon.font = .systemFont(ofSize: 36, weight: .bold)
        icon.textColor = .controlAccentColor
        icon.alignment = .center
        container.addArrangedSubview(icon)

        let title = NSTextField(labelWithString: "Activate NITE Submit")
        title.font = .systemFont(ofSize: 18, weight: .semibold)
        title.textColor = .labelColor
        title.alignment = .center
        container.addArrangedSubview(title)

        let desc = NSTextField(wrappingLabelWithString:
            "Paste the licence key from your purchase confirmation email.")
        desc.font = .systemFont(ofSize: 13)
        desc.textColor = .secondaryLabelColor
        desc.alignment = .center
        container.addArrangedSubview(desc)

        keyField.placeholderString = "NTSUB1-..."
        keyField.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        keyField.alignment = .center
        keyField.bezelStyle = .roundedBezel
        keyField.translatesAutoresizingMaskIntoConstraints = false
        keyField.widthAnchor.constraint(equalToConstant: 400).isActive = true
        container.addArrangedSubview(keyField)

        statusLabel.font = .systemFont(ofSize: 12)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.alignment = .center
        container.addArrangedSubview(statusLabel)

        let buttonRow = NSStackView()
        buttonRow.orientation = .horizontal
        buttonRow.spacing = 12

        let activateButton = NSButton(title: "Activate", target: self,
                                       action: #selector(activateTapped))
        activateButton.bezelStyle = .rounded
        activateButton.keyEquivalent = "\r"
        buttonRow.addArrangedSubview(activateButton)

        container.addArrangedSubview(buttonRow)

        let footer = NSTextField(wrappingLabelWithString:
            "Purchase a licence at nitedsp.co.uk/pricing")
        footer.font = .systemFont(ofSize: 11)
        footer.textColor = .tertiaryLabelColor
        footer.alignment = .center
        container.addArrangedSubview(footer)
    }

    @objc private func activateTapped() {
        let key = keyField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            statusLabel.stringValue = "Please paste your licence key."
            statusLabel.textColor = .systemOrange
            return
        }
        if LicenseEngine.storeLicense(key) {
            statusLabel.stringValue = "Licence activated."
            statusLabel.textColor = .systemGreen
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                self?.onActivated?()
            }
        } else {
            statusLabel.stringValue = "Invalid licence key. Check and try again."
            statusLabel.textColor = .systemRed
        }
    }
}
