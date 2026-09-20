import Foundation
import NiteSubmitCore

func runUpdateEngineTests() {
    print("— UpdateEngine & Appcast RSS Parser")

    // Test 1: Semantic Version Comparison
    let v1 = SemanticVersion("1.0.0")!
    let v2 = SemanticVersion("1.0.1")!
    let v3 = SemanticVersion("1.1.0")!
    let v4 = SemanticVersion("v2.0.0")!

    check(v1 < v2, "1.0.0 < 1.0.1")
    check(v2 < v3, "1.0.1 < 1.1.0")
    check(v3 < v4, "1.1.0 < 2.0.0")
    check(v1 == SemanticVersion("1.0.0"), "1.0.0 == 1.0.0")

    // Test 2: Appcast XML Parsing & Feed Evaluation
    let sampleAppcast = """
    <?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
        <channel>
            <title>NITE Submit Releases</title>
            <item>
                <title>NITE Submit 1.0.1</title>
                <description>Bug fixes and performance improvements for macOS Sequoia.</description>
                <enclosure url="https://releases.nitedsp.com/submit/Submit-1.0.1-macOS.dmg"
                           sparkle:version="1.0.1"
                           length="1153434"
                           sparkle:edSignature="sample_ed25519_signature_hash" />
            </item>
        </channel>
    </rss>
    """.data(using: .utf8)!

    let engine = UpdateEngine()
    let items = engine.parseAppcast(data: sampleAppcast)
    check(items.count == 1, "Appcast parsed 1 item")
    if let first = items.first {
        check(first.versionString == "1.0.1", "Extracted version string 1.0.1")
        check(first.downloadURL.absoluteString == "https://releases.nitedsp.com/submit/Submit-1.0.1-macOS.dmg", "Extracted download URL")
        check(first.edSignature == "sample_ed25519_signature_hash", "Extracted Ed25519 signature")
    }

    // Test 3: Check Status Evaluation
    let status = engine.checkStatus(feedData: sampleAppcast, currentVersionString: "1.0.0")
    switch status {
    case .updateAvailable(let item, let current, let newVer):
        check(current == SemanticVersion("1.0.0"), "Detected current version 1.0.0")
        check(newVer == SemanticVersion("1.0.1"), "Detected new version 1.0.1")
        check(item.versionString == "1.0.1", "Item version string matches")
    default:
        check(false, "Expected updateAvailable status")
    }

    let upToDateStatus = engine.checkStatus(feedData: sampleAppcast, currentVersionString: "1.0.1")
    switch upToDateStatus {
    case .upToDate(let current):
        check(current == SemanticVersion("1.0.1"), "Status up to date for 1.0.1")
    default:
        check(false, "Expected upToDate status")
    }
}
