import Foundation
import NiteSubmitCore

func runPresetTests() {
    suite("NamingPreset") {
        let preset = NamingPreset(id: "dept_rule", displayName: "Dept Rule",
                                   template: "{student_id}_{project_title}",
                                   status: .verified,
                                   requiredFields: ["student_id", "project_title"])

        // Round-trip: encode/decode preserves all fields.
        let data = try! JSONEncoder().encode(preset)
        let decoded = try! JSONDecoder().decode(NamingPreset.self, from: data)
        eq(decoded.id, preset.id, "round-trip preserves id")
        eq(decoded.displayName, preset.displayName, "round-trip preserves displayName")
        eq(decoded.template, preset.template, "round-trip preserves template")
        eq(decoded.status, preset.status, "round-trip preserves status as-is (clamping is an import-time policy, not a Codable one)")
        eq(decoded.requiredFields, preset.requiredFields, "round-trip preserves requiredFields")

        // Import clamp invariant: AppSettings.addImportedPreset must never trust a file's
        // claimed .verified status — an imported preset can only ever be .userCreated.
        var settings = AppSettings()
        settings.addImportedPreset(decoded)
        check(settings.customPresets.count == 1, "imported preset is added")
        eq(settings.customPresets.first?.status, NamingPreset.Status.userCreated,
           "imported preset is clamped to .userCreated even though the source file claimed .verified")

        // Re-importing the same id replaces rather than duplicates.
        var again = decoded
        again.displayName = "Dept Rule (updated)"
        settings.addImportedPreset(again)
        check(settings.customPresets.count == 1, "re-importing the same id replaces, not duplicates")
        eq(settings.customPresets.first?.displayName, "Dept Rule (updated)",
           "replacement keeps the latest imported content")

        // AppSettings persists customPresets across save/load.
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("nitesubmit-preset-tests-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tmp) }
        settings.save(to: tmp)
        let reloaded = AppSettings.load(from: tmp)
        eq(reloaded?.customPresets.count, 1, "custom presets survive save/load round-trip")
        eq(reloaded?.customPresets.first?.status, NamingPreset.Status.userCreated,
           "reloaded custom preset is still .userCreated")
    }
}
