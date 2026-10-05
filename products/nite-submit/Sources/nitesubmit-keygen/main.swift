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
// The in-tree fallback exists for machines that have not moved the key yet,
// but it is exactly the location a `cp tools/*` packaging sweep would pick
// up, so it must be asked for by name every time. An accidental fall-through
// to that path has no business minting real customer licences.
let allowInTreeKey = args.contains("--allow-in-tree-key")
let positional = args.dropFirst().filter { $0 != "--allow-in-tree-key" }
let keyPath: String
if let explicit = positional.first {
    keyPath = explicit
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
    } else if allowInTreeKey {
        let scriptDir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let legacy = scriptDir
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tools/license-private-key.base64").path
        guard FileManager.default.fileExists(atPath: legacy) else {
            fputs("""
            ERROR: --allow-in-tree-key was given but no key exists at
            "tools/license-private-key.base64". The real home for the key is
            $XDG_CONFIG_HOME/nite-submit/license-private-key.base64.

            """, stderr)
            exit(1)
        }
        fputs("""
        WARNING: using the in-tree key at tools/license-private-key.base64.
                 That copy is the real signing key and must NEVER be committed
                 to git, even though tools/ sits inside the repo. It is only
                 here for machines that have not moved it yet. Move the key to
                 $XDG_CONFIG_HOME/nite-submit/license-private-key.base64,
                 delete the copy under tools/, and drop --allow-in-tree-key.

        """, stderr)
        keyPath = legacy
    } else {
        fputs("""
        ERROR: No private key found.

        The key must live at:
            $XDG_CONFIG_HOME/nite-submit/license-private-key.base64
        (defaulting to ~/.config/nite-submit/license-private-key.base64 when
        $XDG_CONFIG_HOME is unset).

        Usage: nitesubmit-keygen [path/to/private-key.base64] [--allow-in-tree-key]

        The in-tree fallback at tools/license-private-key.base64 is NOT used
        unless --allow-in-tree-key is passed explicitly.

        This tool is developer-only and must NEVER be shipped to customers.

        """, stderr)
        exit(1)
    }
}

let privateKey = loadPrivateKey(from: keyPath)
let key = generateLicenseKey(privateKey: privateKey)
print(key)
