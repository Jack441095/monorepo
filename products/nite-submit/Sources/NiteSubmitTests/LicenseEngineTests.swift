import CryptoKit
import Foundation
import NiteSubmitCore

/// The developer signing key is gitignored, so it is present on the machine that
/// builds a release and absent everywhere else. These tests mint real signed keys
/// with it, which is the only way to check the encode/decode pair end to end.
private func devSigningKey() -> Curve25519.Signing.PrivateKey? {
    let keyFile = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // NiteSubmitTests
        .deletingLastPathComponent()   // Sources
        .deletingLastPathComponent()   // nite-submit
        .appendingPathComponent("tools/license-private-key.base64")
    guard let raw = try? String(contentsOf: keyFile, encoding: .utf8),
          let keyData = Data(base64Encoded: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
          let key = try? Curve25519.Signing.PrivateKey(rawRepresentation: keyData)
    else { return nil }
    return key
}

/// The same encoding nitesubmit-keygen performs: little-endian timestamp, then
/// signature, then base64url with the NTSUB1- prefix.
private func mintLicenseKey(_ privateKey: Curve25519.Signing.PrivateKey, issuedAt: Date) -> String {
    var timestamp = UInt32(issuedAt.timeIntervalSince1970).littleEndian
    let payload = Data(bytes: &timestamp, count: 4)
    let signature = try! privateKey.signature(for: payload)
    let b64 = (payload + signature).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
    return "NTSUB1-" + b64
}

func runLicenseEngineTests() {
    suite("LicenseEngine") {
        guard let privateKey = devSigningKey() else {
            check(true, "developer signing key not present — skipping key-minting checks")
            return
        }

        // A genuinely signed key is accepted, and the timestamp survives the
        // round trip to the second. The old decode read the payload in the host's
        // byte order, so this is what pins the wire format to the keygen's.
        scenario("a correctly signed key validates with its issue date intact") {
            let issued = Date(timeIntervalSince1970: 1_788_000_000)
            let key = mintLicenseKey(privateKey, issuedAt: issued)
            let info = LicenseEngine.validate(licenseKey: key)
            check(info?.isValid == true, "a key signed by the dev key validates")
            eq(info?.issueDate.timeIntervalSince1970 ?? 0, issued.timeIntervalSince1970,
               "the little-endian payload decodes back to the exact issue date")
        }

        // Anyone holding the dev key can sign a date decades out, so the signature
        // check alone cannot police the timestamp. validate() refused to look at it
        // at all, so a forged-future key activated the app. The 4-byte payload tops
        // out in February 2106, so 2099 is about as far ahead as this format goes.
        scenario("a key stamped far in the future is refused") {
            let far = Date(timeIntervalSince1970: 4_070_000_000)   // 2099-01-01
            let key = mintLicenseKey(privateKey, issuedAt: far)
            check(LicenseEngine.validate(licenseKey: key) == nil,
                  "a correctly signed key dated 2099 is refused")
        }

        scenario("a key dated tomorrow is still accepted") {
            let tomorrow = Date().addingTimeInterval(24 * 3600)
            let key = mintLicenseKey(privateKey, issuedAt: tomorrow)
            check(LicenseEngine.validate(licenseKey: key)?.isValid == true,
                  "a day of clock skew is tolerated rather than refused")
        }

        scenario("garbage and truncated keys are refused") {
            check(LicenseEngine.validate(licenseKey: "") == nil, "an empty key is refused")
            check(LicenseEngine.validate(licenseKey: "NTSUB1-") == nil, "a prefix with no payload is refused")
            check(LicenseEngine.validate(licenseKey: "not-a-key") == nil, "a key with no prefix is refused")
            let valid = mintLicenseKey(privateKey, issuedAt: Date())
            check(LicenseEngine.validate(licenseKey: String(valid.dropLast(4))) == nil,
                  "a truncated key fails the length or signature check")
        }

        // The old storeLicense wrote and chmod'd under `try?` and returned true
        // either way, so the app announced an activated licence for a key it had
        // not written and asked for it again on the next launch.
        scenario("a store failure is reported instead of returning success") {
            let key = mintLicenseKey(privateKey, issuedAt: Date())
            let fm = FileManager.default
            let locked = fm.temporaryDirectory.appendingPathComponent("nite_lic_\(UUID().uuidString)")
            try fm.createDirectory(at: locked, withIntermediateDirectories: true)
            defer {
                try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: locked.path)
                try? fm.removeItem(at: locked)
            }
            try fm.setAttributes([.posixPermissions: 0o555], ofItemAtPath: locked.path)
            let target = locked.appendingPathComponent("license.key")
            throwsError(try LicenseEngine.storeLicense(key, at: target),
                        "an unwritable destination folder is reported, not swallowed")
            check(!fm.fileExists(atPath: target.path),
                  "the failed store leaves no licence file behind")
        }

        scenario("a valid key is stored owner-only and reads back as licensed") {
            let key = mintLicenseKey(privateKey, issuedAt: Date())
            let fm = FileManager.default
            let dir = fm.temporaryDirectory.appendingPathComponent("nite_lic_ok_\(UUID().uuidString)")
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
            defer { try? fm.removeItem(at: dir) }
            let target = dir.appendingPathComponent("license.key")
            try LicenseEngine.storeLicense(key, at: target)
            check(fm.fileExists(atPath: target.path), "a writable destination stores the key")
            let mode = (try fm.attributesOfItem(atPath: target.path)[.posixPermissions] as? NSNumber)?.intValue
            eq(mode ?? 0, 0o600, "the stored key is not readable by other accounts")
            eq(try String(contentsOf: target, encoding: .utf8), key,
               "the stored key round trips byte for byte")
        }

        scenario("an invalid key is refused before it reaches the disk") {
            let dir = FileManager.default.temporaryDirectory
                .appendingPathComponent("nite_lic_reject_\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: dir) }
            let target = dir.appendingPathComponent("license.key")
            throwsError(try LicenseEngine.storeLicense("NTSUB1-nonsense", at: target),
                        "an invalid key is rejected by the store, not written")
            check(!FileManager.default.fileExists(atPath: target.path),
                  "a rejected key leaves no licence file")
        }
    }
}
