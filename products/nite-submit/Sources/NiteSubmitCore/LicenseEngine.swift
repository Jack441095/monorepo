import CryptoKit
import Foundation

public struct LicenseEngine: Sendable {
    private static let publicKeyBase64 = "kxzasvgjtZIqSnwQ2Gfh9FlkHSt9oHb4slC1YFAas4g="

    public struct LicenseInfo: Sendable {
        public let issueDate: Date
        public let isValid: Bool
    }

    public static func validate(licenseKey: String) -> LicenseInfo? {
        let trimmed = licenseKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.uppercased().hasPrefix("NTSUB1-") else { return nil }
        let encoded = String(trimmed.dropFirst(7))
        guard let data = base64URLDecode(encoded), data.count == 68 else { return nil }
        let payload = data.prefix(4)
        let signature = data.suffix(64)
        guard let pubKeyData = Data(base64Encoded: publicKeyBase64),
              let pubKey = try? Curve25519.Signing.PublicKey(rawRepresentation: pubKeyData)
        else { return nil }
        let isValid = pubKey.isValidSignature(signature, for: payload)
        let timestamp = payload.withUnsafeBytes { $0.load(as: UInt32.self) }
        let issueDate = Date(timeIntervalSince1970: TimeInterval(timestamp))
        return LicenseInfo(issueDate: issueDate, isValid: isValid)
    }

    public static func isLicensed() -> Bool {
        guard let stored = storedLicenseKey() else { return false }
        return validate(licenseKey: stored)?.isValid == true
    }

    @discardableResult
    public static func storeLicense(_ key: String) -> Bool {
        guard let info = validate(licenseKey: key), info.isValid else { return false }
        let url = licenseFileURL()
        try? key.trimmingCharacters(in: .whitespacesAndNewlines)
            .write(to: url, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes(
            [.posixPermissions: 0o600], ofItemAtPath: url.path)
        return true
    }

    public static func removeLicense() {
        try? FileManager.default.removeItem(at: licenseFileURL())
    }

    private static func storedLicenseKey() -> String? {
        guard let raw = try? String(contentsOf: licenseFileURL(), encoding: .utf8) else {
            return nil
        }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func licenseFileURL() -> URL {
        let dir = AppSettings.directory
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        return dir.appendingPathComponent("license.key")
    }

    private static func base64URLDecode(_ string: String) -> Data? {
        var b64 = string
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while b64.count % 4 != 0 { b64.append("=") }
        return Data(base64Encoded: b64)
    }
}

public struct LicenseEntitlement: EntitlementProvider, Sendable {
    public init() {}
    public var isEntitled: Bool { LicenseEngine.isLicensed() }
}
