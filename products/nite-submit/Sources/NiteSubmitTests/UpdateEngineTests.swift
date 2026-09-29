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

private func feed(signing key: Curve25519.Signing.PrivateKey,
                  version: String,
                  url: String,
                  signature: Bool = true,
                  overrideSignature: String? = nil) -> Data {
    let parsed = URL(string: url)!
    let payload = UpdateEngine.signaturePayload(versionString: version, downloadURL: parsed)
    let sig = overrideSignature ?? (try? key.signature(for: payload).base64EncodedString()) ?? ""
    let signatureAttribute = signature ? "sparkle:edSignature=\"\(sig)\"" : ""
    return """
    <?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
        <channel>
            <title>NITE Submit Releases</title>
            <item>
                <title>NITE Submit \(version)</title>
                <description>Bug fixes and performance improvements.</description>
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
    }
}
