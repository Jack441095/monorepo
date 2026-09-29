import CryptoKit
import Foundation

/// Structured semantic version (major.minor.patch) conforming to Comparable and Codable.
public struct SemanticVersion: Comparable, Codable, Equatable, CustomStringConvertible, Sendable {
    public let major: Int
    public let minor: Int
    public let patch: Int
    public let rawString: String

    public init?(_ versionString: String) {
        var cleaned = versionString.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.hasPrefix("v") || cleaned.hasPrefix("V") {
            cleaned = String(cleaned.dropFirst())
        }
        // We reject prerelease/build suffixes outright: "1.2-beta" must not
        // collapse to 1.2.0, or a beta feed entry could masquerade as a
        // stable release and trigger a bogus update prompt.
        let parts = cleaned.split(separator: ".", omittingEmptySubsequences: false)
        guard !parts.isEmpty, parts.count <= 3 else { return nil }
        var numbers: [Int] = []
        for part in parts {
            guard !part.isEmpty,
                  part.allSatisfy({ $0.isNumber }),
                  let value = Int(part) else { return nil }
            numbers.append(value)
        }

        self.major = numbers.count > 0 ? numbers[0] : 0
        self.minor = numbers.count > 1 ? numbers[1] : 0
        self.patch = numbers.count > 2 ? numbers[2] : 0
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

    // The feed itself lives on www; release binaries ship from the releases
    // subdomain, so both hosts are trusted and every other host is refused.
    public static let pinnedFeedHost = "www.nitedsp.co.uk"
    public static let allowedDownloadHosts: Set<String> = ["www.nitedsp.co.uk", "releases.nitedsp.co.uk"]

    // Release Ed25519 public key. The matching private key stays offline with
    // the release owner and is never committed to git.
    public static let updatePublicKeyBase64 = "XrMZt5AZ8Am24TGn67teEw/RfzC0i0owOYVmpTM0s2g="

    private let trustedPublicKeyBase64: String
    private let requireSignature: Bool

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

    public init(trustedPublicKeyBase64: String = UpdateEngine.updatePublicKeyBase64, requireSignature: Bool = true) {
        self.trustedPublicKeyBase64 = trustedPublicKeyBase64
        self.requireSignature = requireSignature
        super.init()
    }

    /// Bytes covered by the enclosure Ed25519 signature: version plus download
    /// URL. Length stays outside the signed payload on purpose, so the release
    /// owner can refresh it with `stat -f%z` on the built zip without
    /// invalidating the signature.
    public static func signaturePayload(versionString: String, downloadURL: URL) -> Data {
        Data((versionString + "\n" + downloadURL.absoluteString).utf8)
    }

    /// Only https URLs on our own hosts may be opened or offered as updates.
    /// Anything else (http, file, custom schemes, foreign hosts) is refused
    /// so a tampered feed cannot point the download button at malware.
    public static func isApprovedDownloadURL(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased(), scheme == "https" else { return false }
        guard let host = url.host?.lowercased() else { return false }
        return allowedDownloadHosts.contains(host)
    }

    /// Verifies the enclosure Ed25519 signature against the trusted release
    /// key. Fails closed: a present-but-invalid signature is refused, and a
    /// missing signature is refused while requireSignature is true.
    public func isTrustedEnclosure(_ item: AppcastItem) -> Bool {
        guard UpdateEngine.isApprovedDownloadURL(item.downloadURL) else { return false }
        guard let signatureString = item.edSignature, !signatureString.isEmpty else {
            return !requireSignature
        }
        guard let signatureData = Data(base64Encoded: signatureString),
              let publicKeyData = Data(base64Encoded: trustedPublicKeyBase64),
              let publicKey = try? Curve25519.Signing.PublicKey(rawRepresentation: publicKeyData)
        else { return false }
        let payload = UpdateEngine.signaturePayload(versionString: item.versionString, downloadURL: item.downloadURL)
        return publicKey.isValidSignature(signatureData, for: payload)
    }

    /// Parses an appcast.xml data payload synchronously or asynchronously.
    public func parseAppcast(data: Data) -> [AppcastItem] {
        parsedItems.removeAll()
        let parser = XMLParser(data: data)
        parser.delegate = self
        // A hostile feed could smuggle file:/// reads or billion-laughs
        // expansion through external entities; we only read plain text nodes.
        parser.shouldResolveExternalEntities = false
        parser.parse()
        return parsedItems
    }

    /// Checks if a newer version is available compared to currentVersion.
    /// An update is offered only when the newest feed entry carries a valid
    /// Ed25519 signature over its exact version and URL; anything unsigned,
    /// tampered, or off-host returns .failed instead of prompting.
    public func checkStatus(feedData: Data, currentVersionString: String) -> UpdateCheckResult {
        guard let currentVer = SemanticVersion(currentVersionString) else {
            return .failed(reason: "Invalid current version string format: \(currentVersionString)")
        }

        let items = parseAppcast(data: feedData)
        if items.isEmpty {
            return .upToDate(currentVersion: currentVer)
        }
        let versionedItems = items.compactMap { item in item.version.map { (item, $0) } }
        guard let (latestItem, latestVer) = versionedItems.max(by: { $0.1 < $1.1 }) else {
            return .failed(reason: "Feed contained no parseable version numbers")
        }
        guard UpdateEngine.isApprovedDownloadURL(latestItem.downloadURL) else {
            return .failed(reason: "Update URL failed approval: \(latestItem.downloadURL.absoluteString)")
        }
        guard isTrustedEnclosure(latestItem) else {
            return .failed(reason: "Update signature missing or invalid for version \(latestItem.versionString)")
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
