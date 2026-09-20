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

func generateLicenseKey(privateKey: Curve25519.Signing.PrivateKey) -> String {
    var timestamp = UInt32(Date().timeIntervalSince1970)
    let payload = Data(bytes: &timestamp, count: 4)
    let signature = try! privateKey.signature(for: payload)
    return "NTSUB1-" + base64URLEncode(payload + signature)
}

let args = CommandLine.arguments
let keyPath: String
if args.count > 1 {
    keyPath = args[1]
} else {
    let scriptDir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let defaultPath = scriptDir
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("tools/license-private-key.base64").path
    if FileManager.default.fileExists(atPath: defaultPath) {
        keyPath = defaultPath
    } else {
        fputs("""
        Usage: nitesubmit-keygen [path/to/private-key.base64]

        Generates a NITE Submit licence key. The private key file defaults to
        tools/license-private-key.base64 relative to the repo root.

        This tool is developer-only and must NEVER be shipped to customers.

        """, stderr)
        exit(1)
    }
}

let privateKey = loadPrivateKey(from: keyPath)
let key = generateLicenseKey(privateKey: privateKey)
print(key)
