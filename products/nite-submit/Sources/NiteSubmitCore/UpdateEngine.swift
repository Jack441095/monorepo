import Foundation

/// Structured semantic version (major.minor.patch) conforming to Comparable and Codable.
public struct SemanticVersion: Comparable, Codable, Equatable, CustomStringConvertible, Sendable {
    public let major: Int
    public let minor: Int
    public let patch: Int
    public let rawString: String

    public init?(_ versionString: String) {
        let cleaned = versionString.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
        let components = cleaned.split(separator: ".").compactMap { Int($0) }
        guard !components.isEmpty else { return nil }

        self.major = components.count > 0 ? components[0] : 0
        self.minor = components.count > 1 ? components[1] : 0
        self.patch = components.count > 2 ? components[2] : 0
        self.rawString = versionString
    }

    public var description: String {
        "\(major).\(minor).\(patch)"
    }

    public static func < (lhs: SemanticVersion, rhs: SemanticVersion) -> Bool {
        if lhs.major != rhs.major { return lhs.major < rhs.major }
        if lhs.minor != rhs.minor { return lhs.minor < rhs.minor }
        return lhs.patch < rhs.patch
    }
}

/// One update entry extracted from an Appcast RSS XML feed.
public struct AppcastItem: Codable, Equatable, Sendable {
    public var title: String
    public var versionString: String
    public var releaseNotes: String
    public var downloadURL: URL
    public var length: Int64?
    public var edSignature: String?
    public var pubDate: Date?

    public init(title: String, versionString: String, releaseNotes: String, downloadURL: URL, length: Int64? = nil, edSignature: String? = nil, pubDate: Date? = nil) {
        self.title = title
        self.versionString = versionString
        self.releaseNotes = releaseNotes
        self.downloadURL = downloadURL
        self.length = length
        self.edSignature = edSignature
        self.pubDate = pubDate
    }

    public var version: SemanticVersion? {
        SemanticVersion(versionString)
    }
}

/// Result of an update check operation.
public enum UpdateCheckResult: Sendable {
    case updateAvailable(item: AppcastItem, currentVersion: SemanticVersion, newVersion: SemanticVersion)
    case upToDate(currentVersion: SemanticVersion)
    case failed(reason: String)
}

/// Lightweight appcast feed parser. Only invoked when the user explicitly
/// chooses "Check for Updates…"; fetches `defaultAppcastURL` at that point
/// and nowhere else in the app.
public final class UpdateEngine: NSObject, XMLParserDelegate, @unchecked Sendable {
    public static let defaultAppcastURL = URL(string: "https://www.nitedsp.co.uk/submit/appcast.xml")!

    // XML Parser State
    private var currentElement = ""
    private var currentTitle = ""
    private var currentDescription = ""
    private var currentVersionString = ""
    private var currentDownloadURL: URL?
    private var currentLength: Int64?
    private var currentEdSignature: String?
    private var currentPubDate: Date?
    private var parsedItems: [AppcastItem] = []

    public override init() {
        super.init()
    }

    /// Parses an appcast.xml data payload synchronously or asynchronously.
    public func parseAppcast(data: Data) -> [AppcastItem] {
        parsedItems.removeAll()
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.parse()
        return parsedItems
    }

    /// Checks if a newer version is available compared to currentVersion.
    public func checkStatus(feedData: Data, currentVersionString: String) -> UpdateCheckResult {
        guard let currentVer = SemanticVersion(currentVersionString) else {
            return .failed(reason: "Invalid current version string format: \(currentVersionString)")
        }

        let items = parseAppcast(data: feedData)
        let versionedItems = items.compactMap { item in item.version.map { (item, $0) } }
        guard let (latestItem, latestVer) = versionedItems.max(by: { $0.1 < $1.1 }) else {
            return .upToDate(currentVersion: currentVer)
        }

        if currentVer < latestVer {
            return .updateAvailable(item: latestItem, currentVersion: currentVer, newVersion: latestVer)
        } else {
            return .upToDate(currentVersion: currentVer)
        }
    }

    // MARK: - XMLParserDelegate

    public func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String : String] = [:]) {
        currentElement = elementName
        if elementName == "item" {
            currentTitle = ""
            currentDescription = ""
            currentVersionString = ""
            currentDownloadURL = nil
            currentLength = nil
            currentEdSignature = nil
            currentPubDate = nil
        } else if elementName == "enclosure" {
            if let urlStr = attributeDict["url"], let url = URL(string: urlStr) {
                currentDownloadURL = url
            }
            if let ver = attributeDict["sparkle:version"] ?? attributeDict["version"] {
                currentVersionString = ver
            }
            if let lenStr = attributeDict["length"], let len = Int64(lenStr) {
                currentLength = len
            }
            if let sig = attributeDict["sparkle:edSignature"] {
                currentEdSignature = sig
            }
        }
    }

    public func parser(_ parser: XMLParser, foundCharacters string: String) {
        // Appended verbatim for title/description: the parser can deliver a
        // single text node as several callbacks (e.g. split around an "&amp;"
        // entity), and a whitespace-only chunk between two word chunks is a
        // real inter-word space that must not be dropped.
        switch currentElement {
        case "title":
            currentTitle += string
        case "description":
            currentDescription += string
        case "sparkle:version":
            let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return }
            currentVersionString += trimmed
        default:
            break
        }
    }

    public func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        if elementName == "item" {
            if let url = currentDownloadURL, !currentVersionString.isEmpty {
                let item = AppcastItem(
                    title: currentTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                    versionString: currentVersionString.trimmingCharacters(in: .whitespacesAndNewlines),
                    releaseNotes: currentDescription.trimmingCharacters(in: .whitespacesAndNewlines),
                    downloadURL: url,
                    length: currentLength,
                    edSignature: currentEdSignature,
                    pubDate: currentPubDate
                )
                parsedItems.append(item)
            }
        }
        currentElement = ""
    }
}
