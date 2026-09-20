import AppKit

/// Quiet editorial palette for Submit's task-focused workflow. The restrained cyan/orange
/// accents borrow the energy of NITE DSP artwork without turning the utility into a control
/// panel. Fixed colours keep AppKit layer-backed views consistent during window creation.
enum NiteSubmitUI {
    static let background = NSColor(calibratedRed: 247 / 255.0, green: 246 / 255.0, blue: 242 / 255.0, alpha: 1) // #F7F6F2
    static let surface = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 0.82)
    static let surfaceRaised = NSColor(calibratedRed: 239 / 255.0, green: 237 / 255.0, blue: 231 / 255.0, alpha: 1) // #EFEDE7
    static let foreground = NSColor(calibratedRed: 22 / 255.0, green: 24 / 255.0, blue: 27 / 255.0, alpha: 1) // #16181B
    static let muted = NSColor(calibratedRed: 91 / 255.0, green: 91 / 255.0, blue: 88 / 255.0, alpha: 1) // #5B5B58
    static let mutedDim = NSColor(calibratedRed: 137 / 255.0, green: 134 / 255.0, blue: 127 / 255.0, alpha: 1) // #89867F
    static let cyan = NSColor(calibratedRed: 29 / 255.0, green: 174 / 255.0, blue: 202 / 255.0, alpha: 1) // #1DAECA
    static let orange = NSColor(calibratedRed: 244 / 255.0, green: 91 / 255.0, blue: 55 / 255.0, alpha: 1) // #F45B37
    static let warning = orange
    static let error = NSColor(calibratedRed: 188 / 255.0, green: 55 / 255.0, blue: 47 / 255.0, alpha: 1) // #BC372F
    static let success = NSColor(calibratedRed: 43 / 255.0, green: 125 / 255.0, blue: 88 / 255.0, alpha: 1) // #2B7D58
    static let border = NSColor(calibratedRed: 218 / 255.0, green: 215 / 255.0, blue: 207 / 255.0, alpha: 1) // #DAD7CF
    static let borderCyan = cyan.withAlphaComponent(0.35)
    static let lcdBackground = NSColor(calibratedRed: 250 / 255.0, green: 249 / 255.0, blue: 246 / 255.0, alpha: 1) // #FAF9F6

    // Consistent Typography Tokens. Monospace is reserved for fontCode — genuine technical
    // readouts (the generated filename, hashes) where showing exact characters matters. Every
    // other label uses the clean system sans-serif; using monospace everywhere was what made the
    // app read as a terminal/console rather than a modern utility.
    static let fontTitle = NSFont.systemFont(ofSize: 12, weight: .semibold)
    static let fontHeader = NSFont.systemFont(ofSize: 11, weight: .semibold)
    static let fontBadge = NSFont.systemFont(ofSize: 10, weight: .semibold)
    static let fontCode = NSFont.monospacedSystemFont(ofSize: 12, weight: .bold)
    static let fontBody = NSFont.systemFont(ofSize: 11, weight: .medium)
    static let fontCaption = NSFont.systemFont(ofSize: 10, weight: .regular)

    static func styleInput(_ field: NSTextField) {
        field.textColor = foreground
        field.backgroundColor = surface
        field.drawsBackground = true
        field.focusRingType = .default
        field.wantsLayer = true
        field.layer?.cornerRadius = 6
        field.layer?.borderWidth = 1
        field.layer?.borderColor = border.cgColor
    }

    static func stylePopup(_ popup: NSPopUpButton) {
        popup.contentTintColor = foreground
    }

    static func stylePrimaryButton(_ button: NSButton) {
        button.bezelStyle = .rounded
        button.contentTintColor = NSColor.white
        button.bezelColor = cyan
    }

    static func styleSecondaryButton(_ button: NSButton) {
        button.bezelStyle = .rounded
        button.contentTintColor = foreground
        button.bezelColor = surfaceRaised
    }
}

// MARK: - Hardware LED Status View (With Animated Pulse Glow)

final class StatusLEDView: NSView {
    enum State {
        case green
        case amber
        case red
        case off

        var color: NSColor {
            switch self {
            case .green: return NiteSubmitUI.success
            case .amber: return NiteSubmitUI.warning
            case .red: return NiteSubmitUI.error
            case .off: return NiteSubmitUI.mutedDim.withAlphaComponent(0.4)
            }
        }
    }

    // Static, non-animated, non-glowing dot — a perpetually pulsing/glowing indicator on up to
    // 9 field rows at once read as dated hardware-skeuomorphism rather than a clean modern status
    // indicator (flagged in this session's UX research pass alongside LCDContainerView's border
    // pulse, removed for the same reason).
    var state: State = .off {
        didSet { needsDisplay = true }
    }

    override var intrinsicContentSize: NSSize {
        NSSize(width: 10, height: 10)
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
    }

    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let rect = bounds.insetBy(dx: 1, dy: 1)

        ctx.setFillColor(state.color.cgColor)
        ctx.fillEllipse(in: rect)

        // Center highlight dot
        let highlight = CGRect(x: rect.midX - 1.5, y: rect.midY + 0.5, width: 3, height: 3)
        ctx.setFillColor(NSColor.white.withAlphaComponent(0.4).cgColor)
        ctx.fillEllipse(in: highlight)
    }
}

// MARK: - Local privacy note

final class PrivacyBadgeView: NSView {
    private let label = NSTextField(labelWithString: "Private by design · files stay on this Mac")

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func setup() {
        wantsLayer = true
        label.font = NiteSubmitUI.fontCaption
        label.textColor = NiteSubmitUI.muted
        label.translatesAutoresizingMaskIntoConstraints = false
        addSubview(label)

        NSLayoutConstraint.activate([
            label.topAnchor.constraint(equalTo: topAnchor, constant: 4),
            label.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -4),
            label.leadingAnchor.constraint(equalTo: leadingAnchor),
            label.trailingAnchor.constraint(equalTo: trailingAnchor),
        ])
    }
}

// MARK: - Process Pipeline Stepper View (With Smooth Fade Transitions)

final class PipelineStepperView: NSView {
    enum Step: Int, CaseIterable {
        case input = 0
        case analysis = 1
        case intelligence = 2
        case recommendation = 3
        case action = 4

        var title: String {
            switch self {
            case .input: return "Add file"
            case .analysis: return "Detect"
            case .intelligence: return "Review"
            case .recommendation: return "Approve"
            case .action: return "Done"
            }
        }
    }

    var activeStep: Step = .input {
        didSet {
            animateTransition()
        }
    }

    private var labelViews: [NSTextField] = []
    private var dotViews: [NSView] = []

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func setup() {
        wantsLayer = true
        layer?.backgroundColor = NiteSubmitUI.surface.cgColor
        layer?.cornerRadius = 6
        layer?.borderWidth = 1
        layer?.borderColor = NiteSubmitUI.border.cgColor

        let stack = NSStackView()
        stack.orientation = .horizontal
        stack.spacing = 6
        stack.alignment = .centerY
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)

        for (index, step) in Step.allCases.enumerated() {
            if index > 0 {
                let line = NSView()
                line.wantsLayer = true
                line.layer?.backgroundColor = NiteSubmitUI.border.cgColor
                line.widthAnchor.constraint(equalToConstant: 16).isActive = true
                line.heightAnchor.constraint(equalToConstant: 1).isActive = true
                stack.addArrangedSubview(line)
            }

            let dot = NSView()
            dot.wantsLayer = true
            dot.layer?.cornerRadius = 3
            dot.layer?.backgroundColor = NiteSubmitUI.mutedDim.cgColor
            dot.widthAnchor.constraint(equalToConstant: 6).isActive = true
            dot.heightAnchor.constraint(equalToConstant: 6).isActive = true
            dotViews.append(dot)

            let label = NSTextField(labelWithString: step.title)
            label.font = NiteSubmitUI.fontHeader

            let stepGroup = NSStackView(views: [dot, label])
            stepGroup.orientation = .horizontal
            stepGroup.spacing = 4
            stepGroup.alignment = .centerY

            stack.addArrangedSubview(stepGroup)
            labelViews.append(label)
        }

        updateLabels()

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: topAnchor, constant: 6),
            stack.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -6),
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12),
        ])
    }

    private func animateTransition() {
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.25
            ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            updateLabels()
        }
    }

    private func updateLabels() {
        for (index, step) in Step.allCases.enumerated() {
            guard index < labelViews.count, index < dotViews.count else { continue }
            let label = labelViews[index]
            let dot = dotViews[index]
            if step == activeStep {
                let stepColor = (step == .recommendation) ? NiteSubmitUI.success : NiteSubmitUI.cyan
                label.animator().textColor = stepColor
                dot.layer?.backgroundColor = stepColor.cgColor
            } else if index < activeStep.rawValue {
                label.animator().textColor = NiteSubmitUI.success
                dot.layer?.backgroundColor = NiteSubmitUI.success.cgColor
            } else {
                label.animator().textColor = NiteSubmitUI.mutedDim
                dot.layer?.backgroundColor = NiteSubmitUI.mutedDim.withAlphaComponent(0.4).cgColor
            }
        }
    }
}

// MARK: - LCD Monitor Readout Display Container View (With Animated Border Pulse)

final class LCDContainerView: NSView {
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func setup() {
        // Static border, not an infinitely pulsing glow (removed in this session's UX pass —
        // see StatusLEDView for the same change and rationale).
        wantsLayer = true
        layer?.cornerRadius = 12
        layer?.backgroundColor = NiteSubmitUI.lcdBackground.cgColor
        layer?.borderWidth = 1
        layer?.borderColor = NiteSubmitUI.border.cgColor
    }
}


