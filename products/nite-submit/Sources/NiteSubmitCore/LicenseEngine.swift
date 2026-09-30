import CryptoKit
import Foundation

public struct LicenseEngine: Sendable {
    private static let publicKeyBase64 = "kxzasvgjtZIqSnwQ2Gfh9FlkHSt9oHb4slC1YFAas4g="

    /// A key stamped more than a day ahead is not a purchase made early, it is a
    /// hand-rolled one, and the signature check cannot tell the difference because
    /// anyone holding the dev key can sign a date 100 years out. A whole day of
    /// slack covers a machine whose clock is minutes out.
    private static let maxClockSkew: TimeInterval = 86_400

    public struct LicenseInfo: Sendable {
        public let issueDate: Date
        public let isValid: Bool
    }

    /// Wire format, shared with nitesubmit-keygen: a 4-byte little-endian Unix
    /// timestamp followed by a 64-byte Ed25519 signature, 68 bytes in total.
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
        guard isValid else { return nil }
        // load(as:) would have read these four bytes in this machine's byte order
        // and demanded an aligned pointer, so a big-endian build decoded a garbage
        // date and an odd offset trapped. loadUnaligned plus littleEndian decodes
        // the keygen's encoding on every platform.
        let timestamp = payload.withUnsafeBytes { $0.loadUnaligned(as: UInt32.self).littleEndian }
        let issueDate = Date(timeIntervalSince1970: TimeInterval(timestamp))
        guard issueDate <= Date().addingTimeInterval(maxClockSkew) else { return nil }
        return LicenseInfo(issueDate: issueDate, isValid: isValid)
    }

    public static func isLicensed() -> Bool {
        guard let stored = storedLicenseKey() else { return false }
        return validate(licenseKey: stored)?.isValid == true
    }

    /// Persist a licence key, and say so when it did not reach the disk. This used
    /// to write and chmod under `try?` and then return true no matter what, so the
    /// app reported an activated licence for a key it had never stored: the next
    /// launch asked for the key again with nothing on screen to explain why.
    public static func storeLicense(_ key: String) throws {
        try storeLicense(key, at: licenseFileURL())
    }

    /// Same, with the destination stated. The app passes the settings directory;
    /// naming the file keeps the failure path reachable from a test without
    /// writing into the real settings folder.
    public static func storeLicense(_ key: String, at url: URL) throws {
        guard let info = validate(licenseKey: key), info.isValid else {
            throw LicenseStoreError.rejected
        }
        do {
            try key.trimmingCharacters(in: .whitespacesAndNewlines)
                .write(to: url, atomically: true, encoding: .utf8)
            // 0o600: the key is a bearer credential, so it must not be world-readable.
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600], ofItemAtPath: url.path)
        } catch {
            throw LicenseStoreError.notPersisted(error.localizedDescription)
        }
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

/// Why a licence did not get stored. Kept apart from a rejected key because the
/// student's next move is different: one means "check the key", the other means
/// "check the folder".
public enum LicenseStoreError: Error, LocalizedError, Sendable {
    case rejected
    case notPersisted(String)

    public var errorDescription: String? {
        switch self {
        case .rejected:
            return "That licence key is not valid."
        case .notPersisted(let reason):
            return "Your licence is valid but could not be saved: \(reason). Check that NiteSubmit can write to your Application Support folder."
        }
    }
}

public struct LicenseEntitlement: EntitlementProvider, Sendable {
    public init() {}
    public var isEntitled: Bool { LicenseEngine.isLicensed() }
}