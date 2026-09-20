import AppKit
import NiteSubmitCore
import UniformTypeIdentifiers

/// Drag-and-drop zone accepting PDF files, media assets, and folders.
final class DropZoneView: NSView {
    /// Called with dropped/picked files or folders. Order matches selection.
    var onDrop: (([URL]) -> Void)?
    private var isHighlighted = false

    override init(frame: NSRect) {
        super.init(frame: frame)
        registerForDraggedTypes([.fileURL])
        wantsLayer = true
        setAccessibilityLabel("Drop files or folder to begin")
        setAccessibilityHelp("Drop files or a folder here or click to browse. Documents are read locally and never uploaded.")
    }

    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ dirtyRect: NSRect) {
        guard NSGraphicsContext.current != nil else { return }

        let strokeColor: NSColor = isHighlighted ? NiteSubmitUI.cyan : NiteSubmitUI.border
        let fillColor: NSColor = isHighlighted ? NiteSubmitUI.cyan.withAlphaComponent(0.08) : NiteSubmitUI.surface

        let rect = bounds.insetBy(dx: 1, dy: 1)
        let path = NSBezierPath(roundedRect: rect, xRadius: 16, yRadius: 16)

        fillColor.setFill()
        path.fill()

        strokeColor.setStroke()
        path.lineWidth = isHighlighted ? 2.0 : 1.0

        if !isHighlighted {
            let dash: [CGFloat] = [5, 5]
            path.setLineDash(dash, count: 2, phase: 0)
        }

        path.stroke()

        // A few restrained, original curves bring the NITE artwork language into the empty state
        // without reproducing the reference artwork or competing with the drop instruction.
        NSGraphicsContext.saveGraphicsState()
        let motifRect = NSRect(x: bounds.maxX - min(150, bounds.width * 0.28), y: 12,
                               width: min(125, bounds.width * 0.24), height: bounds.height - 24)
        let curves: [(NSColor, CGFloat, CGFloat)] = [
            (NiteSubmitUI.cyan.withAlphaComponent(0.42), 0.18, 0.74),
            (NiteSubmitUI.orange.withAlphaComponent(0.42), 0.42, 0.38),
            (NiteSubmitUI.foreground.withAlphaComponent(0.16), 0.66, 0.58),
        ]
        for (colour, start, end) in curves {
            let curve = NSBezierPath()
            curve.move(to: NSPoint(x: motifRect.minX, y: motifRect.minY + motifRect.height * start))
            curve.curve(to: NSPoint(x: motifRect.maxX, y: motifRect.minY + motifRect.height * end),
                        controlPoint1: NSPoint(x: motifRect.minX + motifRect.width * 0.30, y: motifRect.maxY),
                        controlPoint2: NSPoint(x: motifRect.minX + motifRect.width * 0.70, y: motifRect.minY))
            colour.setStroke()
            curve.lineWidth = 1.15
            curve.stroke()
        }
        NSGraphicsContext.restoreGraphicsState()

        // Two-line layout, optically offset left to leave the artwork breathing room.
        let para = NSMutableParagraphStyle()
        para.alignment = .center

        let titleAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 15, weight: .semibold),
            .foregroundColor: isHighlighted ? NiteSubmitUI.cyan : NiteSubmitUI.foreground,
            .paragraphStyle: para,
        ]

        let subAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .regular),
            .foregroundColor: NiteSubmitUI.muted,
            .paragraphStyle: para,
        ]

        let titleString = isHighlighted ? "Release to add" : "Drop your submission here"
        let subString = "or click to choose a PDF, document, media file or folder"

        let titleSize = (titleString as NSString).size(withAttributes: titleAttrs)
        let subSize = (subString as NSString).size(withAttributes: subAttrs)

        let totalHeight = titleSize.height + subSize.height + 4
        let startY = (bounds.height - totalHeight) / 2 + subSize.height + 4

        let textCentre = bounds.midX - min(46, bounds.width * 0.08)
        (titleString as NSString).draw(at: NSPoint(x: textCentre - titleSize.width / 2, y: startY), withAttributes: titleAttrs)
        (subString as NSString).draw(at: NSPoint(x: textCentre - subSize.width / 2, y: startY - subSize.height - 4), withAttributes: subAttrs)
    }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        isHighlighted = true
        needsDisplay = true
        return sender.draggingPasteboard.canReadObject(forClasses: [NSURL.self]) ? .copy : []
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        isHighlighted = false
        needsDisplay = true
    }

    override func draggingEnded(_ sender: NSDraggingInfo) {
        isHighlighted = false
        needsDisplay = true
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        isHighlighted = false
        needsDisplay = true
        guard let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self]) as? [URL] else {
            return false
        }
        let validFiles = urls.filter { !$0.lastPathComponent.hasPrefix(".") }
        guard !validFiles.isEmpty else { return false }
        onDrop?(validFiles)
        return true
    }

    override func mouseDown(with event: NSEvent) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        if panel.runModal() == .OK, !panel.urls.isEmpty { onDrop?(panel.urls) }
    }

    override var acceptsFirstResponder: Bool { true }
}
