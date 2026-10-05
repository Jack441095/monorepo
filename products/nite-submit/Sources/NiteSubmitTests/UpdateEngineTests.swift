import Foundation
import CryptoKit
import NiteSubmitCore

/// Builds a throwaway Ed25519 key pair so the signature gate can be exercised
/// for real instead of stubbed. The production release key stays in
/// `UpdateEngine.updatePublicKeyBase64` and is never used to sign here.
private func makeTestKeyPair() throws -> (privateKey: Curve25519.Signing.PrivateKey, publicKeyBase64: String) {
    let key = Curve25519.Signing.PrivateKey()
    return (key, key.publicKey.rawRepresentation.base64EncodedString())
}

private func rfc2822(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(identifier: "GMT")
    formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss Z"
    return formatter.string(from: date)
}

/// An hour in the past: old enough to clear the one-day future-date gate with
/// room to spare, recent enough that no test run can drift past it.
private func ordinaryPubDate() -> String {
    rfc2822(Date().addingTimeInterval(-3_600)) // seconds per hour
}

private func feed(signing key: Curve25519.Signing.PrivateKey,
                  version: String,
                  url: String,
                  signature: Bool = true,
                  overrideSignature: String? = nil,
                  pubDate: String? = ordinaryPubDate()) -> Data {
    let parsed = URL(string: url)!
    let payload = UpdateEngine.signaturePayload(versionString: version, downloadURL: parsed)
    let sig = overrideSignature ?? (try? key.signature(for: payload).base64EncodedString()) ?? ""
    let signatureAttribute = signature ? "sparkle:edSignature=\"\(sig)\"" : ""
    // nil pubDate omits the element entirely (the missing-date case); a
    // non-nil string lands verbatim, so tests can feed garbage in.
    let pubDateElement = pubDate.map { "<pubDate>\($0)</pubDate>" } ?? ""
    return """
    <?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
        <channel>
            <title>NITE Submit Releases</title>
            <item>
                <title>NITE Submit \(version)</title>
                <description>Bug fixes and performance improvements.</description>
                \(pubDateElement)
                <enclosure url="\(url)" sparkle:version="\(version)" length="1153434" \(signatureAttribute) />
            </item>
        </channel>
    </rss>
    """.data(using: .utf8)!
}

public func runUpdateEngineTests() {
    suite("UpdateEngine & Appcast RSS Parser") {
        let v1 = SemanticVersion("1.0.0")!
        let v2 = SemanticVersion("1.0.1")!
        let v3 = SemanticVersion("1.1.0")!
        let v4 = SemanticVersion("v2.0.0")!

        check(v1 < v2, "1.0.0 < 1.0.1")
        check(v2 < v3, "1.0.1 < 1.1.0")
        check(v3 < v4, "1.1.0 < 2.0.0")
        check(v1 == SemanticVersion("1.0.0"), "1.0.0 == 1.0.0")

        // B10: a prerelease must not masquerade as its release. The old parser
        // dropped every non-numeric component, so "1.1-beta" collapsed to
        // 1.1.0 and compared equal to the shipped 1.1.0.
        check(SemanticVersion("1.1-beta") == nil, "1.1-beta is not a valid release version")
        check(SemanticVersion("2.0rc1") == nil, "2.0rc1 is not a valid release version")
        check(SemanticVersion("") == nil, "an empty version string is refused")

        guard let keys = try? makeTestKeyPair() else {
            check(false, "test key pair generation")
            return
        }
        let engine = UpdateEngine(trustedPublicKeyBase64: keys.publicKeyBase64, requireSignature: true)
        let signedFeed = feed(signing: keys.privateKey,
                              version: "1.0.1",
                              url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip")

        let items = engine.parseAppcast(data: signedFeed)
        check(items.count == 1, "Appcast parsed 1 item")
        if let first = items.first {
            check(first.versionString == "1.0.1", "Extracted version string 1.0.1")
            check(first.downloadURL.absoluteString == "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                  "Extracted download URL")
            check(first.length == 1153434, "Extracted enclosure length")
            check(first.edSignature?.isEmpty == false, "Extracted Ed25519 signature")
            check(first.pubDate != nil, "Extracted and parsed pubDate")
        }

        switch engine.checkStatus(feedData: signedFeed, currentVersionString: "1.0.0") {
        case .updateAvailable(let item, let current, let newVer):
            check(current == SemanticVersion("1.0.0"), "Detected current version 1.0.0")
            check(newVer == SemanticVersion("1.0.1"), "Detected new version 1.0.1")
            check(item.versionString == "1.0.1", "Item version string matches")
        default:
            check(false, "Expected updateAvailable status for a correctly signed feed")
        }

        switch engine.checkStatus(feedData: signedFeed, currentVersionString: "1.0.1") {
        case .upToDate(let current):
            check(current == SemanticVersion("1.0.1"), "Status up to date for 1.0.1")
        default:
            check(false, "Expected upToDate status when already on the signed version")
        }

        // B2: every one of these is a feed we must refuse rather than offer
        // to open, because a tampered feed can otherwise aim the download
        // button at malware on any host.
        let unsignedFeed = feed(signing: keys.privateKey, version: "1.0.1",
                                url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                                signature: false)
        if case .updateAvailable = engine.checkStatus(feedData: unsignedFeed, currentVersionString: "1.0.0") {
            check(false, "an unsigned enclosure is refused")
        } else {
            check(true, "an unsigned enclosure is refused")
        }

        let tamperedFeed = feed(signing: keys.privateKey, version: "1.0.1",
                                url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                                overrideSignature: Data(repeating: 7, count: 64).base64EncodedString())
        if case .updateAvailable = engine.checkStatus(feedData: tamperedFeed, currentVersionString: "1.0.0") {
            check(false, "a tampered signature is refused")
        } else {
            check(true, "a tampered signature is refused")
        }

        let wrongKey = UpdateEngine(trustedPublicKeyBase64: Curve25519.Signing.PrivateKey().publicKey.rawRepresentation.base64EncodedString(),
                                    requireSignature: true)
        if case .updateAvailable = wrongKey.checkStatus(feedData: signedFeed, currentVersionString: "1.0.0") {
            check(false, "a signature from an unknown key is refused")
        } else {
            check(true, "a signature from an unknown key is refused")
        }

        check(!UpdateEngine.isApprovedDownloadURL(URL(string: "http://releases.nitedsp.co.uk/x.zip")!),
              "plain http download URL is refused")
        check(!UpdateEngine.isApprovedDownloadURL(URL(string: "https://evil.example/x.zip")!),
              "off-host download URL is refused")
        check(!UpdateEngine.isApprovedDownloadURL(URL(string: "file:///etc/passwd")!),
              "file scheme download URL is refused")
        check(UpdateEngine.isApprovedDownloadURL(URL(string: "https://releases.nitedsp.co.uk/x.zip")!),
              "our own https release host is approved")

        let permissive = UpdateEngine(trustedPublicKeyBase64: keys.publicKeyBase64, requireSignature: false)
        if case .updateAvailable = permissive.checkStatus(feedData: unsignedFeed, currentVersionString: "1.0.0") {
            check(true, "requireSignature=false is the only way an unsigned feed is offered")
        } else {
            check(false, "requireSignature=false is the only way an unsigned feed is offered")
        }

        // A signed entry whose pubDate sits more than a day out cannot be
        // trusted as "released now": the signature proves ownership, not
        // freshness. LicenseEngine already refuses such timestamps; the
        // updater must refuse them too or a forged "tomorrow's" release wins
        // the version race early.
        let futureFeed = feed(signing: keys.privateKey, version: "1.0.1",
                              url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                              pubDate: rfc2822(Date().addingTimeInterval(2 * 86_400))) // 2 days out
        if case .updateAvailable = engine.checkStatus(feedData: futureFeed, currentVersionString: "1.0.0") {
            check(false, "a future-dated entry is refused")
        } else {
            check(true, "a future-dated entry is refused")
        }

        // Present-but-garbled pubDate is as good as no date: parsing must
        // fail closed rather than offer an update we cannot date.
        let invalidDateFeed = feed(signing: keys.privateKey, version: "1.0.1",
                                   url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                                   pubDate: "next Thursday, probably")
        if case .updateAvailable = engine.checkStatus(feedData: invalidDateFeed, currentVersionString: "1.0.0") {
            check(false, "an unreadable pubDate is refused")
        } else {
            check(true, "an unreadable pubDate is refused")
        }

        // A missing pubDate element is the third shape of the same failure:
        // no honest release ships without a date, and a stripped one may be
        // an attempt to dodge the future-date check.
        let missingDateFeed = feed(signing: keys.privateKey, version: "1.0.1",
                                   url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.1-macOS.zip",
                                   pubDate: nil)
        if case .updateAvailable = engine.checkStatus(feedData: missingDateFeed, currentVersionString: "1.0.0") {
            check(false, "a missing pubDate is refused when a signature is expected")
        } else {
            check(true, "a missing pubDate is refused when a signature is expected")
        }

        // Correctly signed but old: age alone must never trigger an upgrade
        // prompt. The entry below has a real signature over version 1.0.0
        // and a date in 2024, yet the installed 1.2.0 is newer, so the only
        // honest answer is "up to date".
        let oldValidFeed = feed(signing: keys.privateKey, version: "1.0.0",
                                url: "https://releases.nitedsp.co.uk/submit/Submit-1.0.0-macOS.zip",
                                pubDate: "Wed, 20 Mar 2024 12:00:00 +0000")
        switch engine.checkStatus(feedData: oldValidFeed, currentVersionString: "1.2.0") {
        case .upToDate:
            check(true, "an old, validly signed entry does not auto-win over a newer installed version")
        default:
            check(false, "an old, validly signed entry does not auto-win over a newer installed version")
        }

        // ...while the same old entry remains an eligible upgrade when its
        // version still beats what is installed: pubDate gates freshness and
        // signature gates authenticity, but version is still the only
        // candidacy test.
        switch engine.checkStatus(feedData: oldValidFeed, currentVersionString: "0.9.0") {
        case .updateAvailable:
            check(true, "an old, validly signed entry upgrades only when it wins the version comparison")
        default:
            check(false, "an old, validly signed entry upgrades only when it wins the version comparison")
        }

        // The feed we actually publish lives in web/appcast.xml. It shipped
        // without a length or an edSignature for a while, which is a silently
        // dead updater: the parser saw the enclosure, the signature gate
        // refused it, and nothing ever said why. tools/update_appcast.sh writes
        // both attributes from the built zip and the offline release key.
        let shippedFeedURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("web/appcast.xml")
        guard let shippedFeed = try? Data(contentsOf: shippedFeedURL) else {
            check(false, "web/appcast.xml is present at \(shippedFeedURL.path)")
            return
        }
        check(true, "web/appcast.xml is present at \(shippedFeedURL.lastPathComponent)")
        let shippedItems = engine.parseAppcast(data: shippedFeed)
        check(!shippedItems.isEmpty, "the shipped appcast parses into at least one enclosure")
        for item in shippedItems {
            check(item.edSignature != nil,
                  "shipped \(item.versionString) enclosure carries a sparkle:edSignature attribute")
            check(item.length != nil,
                  "shipped \(item.versionString) enclosure carries a length attribute")
            check(UpdateEngine.isApprovedDownloadURL(item.downloadURL),
                  "shipped \(item.versionString) download URL is on an approved host")
        }
    }
}
