import CryptoKit
import Foundation

func base64URLEncode(_ data: Data) -> String {
    data.base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}

func loadPrivateKey(from path: String) -> Curve25519.Signing.PrivateKey {
    guard let raw = try? String(contentsOfFile: path, encoding: .utf8) else {
        fputs("ERROR: Cannot read private key file at \(path)\n", stderr)
        exit(1)
    }
    let b64 = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let keyData = Data(base64Encoded: b64) else {
        fputs("ERROR: Private key file is not valid base64.\n", stderr)
        exit(1)
    }
    do {
        return try Curve25519.Signing.PrivateKey(rawRepresentation: keyData)
    } catch {
        fputs("ERROR: Invalid Ed25519 private key: \(error)\n", stderr)
        exit(1)
    }
}

func generateLicenseKey(privateKey: Curve25519.Signing.PrivateKey,
                        issuedAt: Date = Date()) -> String {
    // Wire format, matching LicenseEngine.validate: a 4-byte little-endian Unix
    // timestamp then the 64-byte signature. Data(bytes:) copied the host's memory
    // layout, which happened to be little-endian on every Mac but is not the
    // format, so a key minted on a big-endian build would have decoded as a date
    // in the year 6000-something.
    var timestamp = UInt32(issuedAt.timeIntervalSince1970).littleEndian
    let payload = Data(bytes: &timestamp, count: 4)
    let signature = try! privateKey.signature(for: payload)
    return "NTSUB1-" + base64URLEncode(payload + signature)
}

let args = CommandLine.arguments
let keyPath: String
if args.count > 1 {
    keyPath = args[1]
} else {
    // The licence signing key lives outside the source tree on purpose. It used
    // to sit in tools/ beside the packaging scripts, one `cp tools/*` away from
    // the bundle: anything that cannot mint customer licence keys must never be
    // inside a product we ship.
    let configRoot = ProcessInfo.processInfo.environment["XDG_CONFIG_HOME"]
        ?? URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent(".config").path
    let preferred = URL(fileURLWithPath: configRoot)
        .appendingPathComponent("nite-submit")
        .appendingPathComponent("license-private-key.base64").path
    if FileManager.default.fileExists(atPath: preferred) {
        keyPath = preferred
    } else {
        let scriptDir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let legacy = scriptDir
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tools/license-private-key.base64").path
        guard FileManager.default.fileExists(atPath: legacy) else {
            fputs("""
            Usage: nitesubmit-keygen [path/to/private-key.base64]

            Generates a NITE Submit licence key. The private key file defaults to
            $XDG_CONFIG_HOME/nite-submit/license-private-key.base64 (falling back
            to ~/.config/nite-submit/license-private-key.base64).

            This tool is developer-only and must NEVER be shipped to customers.

            """, stderr)
            exit(1)
        }
        fputs("""
        WARNING: using the in-tree key at tools/license-private-key.base64.
                 That location is deprecated and sits where a packaging sweep could
                 pick it up. Move the key to
                 $XDG_CONFIG_HOME/nite-submit/license-private-key.base64
                 and delete the copy under tools/.

        """, stderr)
        keyPath = legacy
    }
}

let privateKey = loadPrivateKey(from: keyPath)
let key = generateLicenseKey(privateKey: privateKey)
print(key)
