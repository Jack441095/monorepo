import Foundation

/// One queue row paired with its own review decision. The app keeps approval
/// per document (each row is reviewed on its own), so the archive step must
/// filter on this rather than trusting the single selected item's flag alone —
/// otherwise approving one file would silently include unreviewed ones.
public struct ArchiveQueueEntry: Sendable {
    public var url: URL
    public var isApproved: Bool

    public init(url: URL, isApproved: Bool) {
        self.url = url
        self.isApproved = isApproved
    }
}

/// URLs that are actually allowed into the archive: only the approved rows.
/// An empty queue falls through untouched so the single-file path (no queue
/// rows, just the loaded document) keeps its existing controller-side gate.
public func approvedArchiveSources(from entries: [ArchiveQueueEntry]) -> [URL] {
    entries.filter { $0.isApproved }.map { $0.url }
}
