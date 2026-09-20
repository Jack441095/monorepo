import Foundation

/// Local settings persisted to ~/Library/Application Support/NiteSubmit/settings.json.
/// NEVER stores PDF contents, document text, or document history.
public struct AppSettings: Codable, Sendable {
    public var template: String
    public var presetId: String
    public var renameMode: FileOperationMode
    public var caseStyle: FilenameSanitizer.CaseStyle
    public var universityPresetId: String
    /// Optional user-provided identity applied only when a document has no
    /// student number of its own. Stored locally with the other preferences.
    public var defaultStudentId: String
    /// Prevents the optional onboarding prompt from interrupting every launch
    /// when a user chooses “Not now”. The editable field remains available.
    public var hasPromptedForDefaultStudentId: Bool
    /// Optional content rule for the first two pages of the PDF. This is
    /// independent of the filename template and defaults to no rule.
    public var documentIdentityPolicy: DocumentIdentityPolicy
    /// Naming presets imported from a `.submitrule.json` file (e.g. shared by a
    /// tutor or another student). Import always clamps `status` to `.userCreated`
    /// regardless of what the file claims — an imported preset can never present
    /// as `.verified`.
    public var customPresets: [NamingPreset]

    public init(template: String = "{student_id}_{project_title}",
                presetId: String = "id_project",
                renameMode: FileOperationMode = .createCopy,
                caseStyle: FilenameSanitizer.CaseStyle = .keepOriginal,
                universityPresetId: String = "custom",
                defaultStudentId: String = "",
                hasPromptedForDefaultStudentId: Bool = false,
                documentIdentityPolicy: DocumentIdentityPolicy = .noRule,
                customPresets: [NamingPreset] = []) {
        self.template = template
        self.presetId = presetId
        self.renameMode = renameMode
        self.caseStyle = caseStyle
        self.universityPresetId = universityPresetId
        self.defaultStudentId = defaultStudentId
        self.hasPromptedForDefaultStudentId = hasPromptedForDefaultStudentId
        self.documentIdentityPolicy = documentIdentityPolicy
        self.customPresets = customPresets
    }

    private enum CodingKeys: String, CodingKey {
        case template, presetId, renameMode, caseStyle, universityPresetId,
             defaultStudentId, hasPromptedForDefaultStudentId, documentIdentityPolicy,
             customPresets
    }

    /// Decode older settings files without discarding their other preferences.
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        template = try c.decodeIfPresent(String.self, forKey: .template)
            ?? "{student_id}_{project_title}"
        presetId = try c.decodeIfPresent(String.self, forKey: .presetId)
            ?? "id_project"
        renameMode = try c.decodeIfPresent(FileOperationMode.self, forKey: .renameMode)
            ?? .createCopy
        caseStyle = try c.decodeIfPresent(FilenameSanitizer.CaseStyle.self, forKey: .caseStyle)
            ?? .keepOriginal
        universityPresetId = try c.decodeIfPresent(String.self, forKey: .universityPresetId)
            ?? "custom"
        defaultStudentId = try c.decodeIfPresent(String.self, forKey: .defaultStudentId) ?? ""
        hasPromptedForDefaultStudentId = try c.decodeIfPresent(Bool.self,
                                                               forKey: .hasPromptedForDefaultStudentId)
            ?? false
        documentIdentityPolicy = try c.decodeIfPresent(DocumentIdentityPolicy.self,
                                                        forKey: .documentIdentityPolicy)
            ?? .noRule
        customPresets = try c.decodeIfPresent([NamingPreset].self, forKey: .customPresets) ?? []
    }

    /// Add an imported preset, forcing its provenance to `.userCreated` regardless of what the
    /// source file claimed — an imported preset must never present as `.verified`. Replaces any
    /// existing custom preset with the same id.
    public mutating func addImportedPreset(_ preset: NamingPreset) {
        var clamped = preset
        clamped.status = .userCreated
        customPresets.removeAll { $0.id == clamped.id }
        customPresets.append(clamped)
    }

    static var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("NiteSubmit", isDirectory: true)
    }

    static var fileURL: URL { directory.appendingPathComponent("settings.json") }

    public static func load() -> AppSettings {
        guard let data = try? Data(contentsOf: fileURL),
              let s = try? JSONDecoder().decode(AppSettings.self, from: data) else {
            return AppSettings()
        }
        // Repair permissions for settings created by an older build. This is
        // intentionally done after a successful decode so a malformed file
        // is never overwritten during recovery.
        s.save()
        return s
    }

    public func save() {
        let fm = FileManager.default
        try? fm.createDirectory(at: Self.directory, withIntermediateDirectories: true,
                                attributes: [.posixPermissions: 0o700])
        // The settings file contains the user's saved student number. Keep
        // both the containing directory and the file private even when an
        // older install created them with broader default permissions.
        try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: Self.directory.path)
        guard let data = try? JSONEncoder().encode(self) else { return }
        try? data.write(to: Self.fileURL, options: .atomic)
        try? fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: Self.fileURL.path)
    }

    /// Apply a user edit to a preset-backed template. Editing the template
    /// makes it a custom rule, so the visible profile and the persisted state
    /// cannot continue to claim that an old preset is active.
    public mutating func applyCustomTemplate(_ value: String) {
        template = value
        presetId = "custom"
        universityPresetId = "custom"
    }

    /// Test seam: load/save against an explicit directory.
    public static func load(from dir: URL) -> AppSettings? {
        let url = dir.appendingPathComponent("settings.json")
        guard let data = try? Data(contentsOf: url),
              let s = try? JSONDecoder().decode(AppSettings.self, from: data) else { return nil }
        s.save(to: dir)
        return s
    }

    public func save(to dir: URL) {
        let fm = FileManager.default
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true,
                                attributes: [.posixPermissions: 0o700])
        try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: dir.path)
        guard let data = try? JSONEncoder().encode(self) else { return }
        let url = dir.appendingPathComponent("settings.json")
        try? data.write(to: url, options: .atomic)
        try? fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

public protocol EntitlementProvider: Sendable {
    var isEntitled: Bool { get }
}
