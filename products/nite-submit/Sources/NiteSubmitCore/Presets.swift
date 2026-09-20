import Foundation

/// A naming rule preset. V1 ships CUSTOM plus clearly-labelled generic examples.
/// No preset claims official university endorsement.
public struct NamingPreset: Codable, Identifiable, Hashable, Sendable {
    public enum Status: String, Codable, Sendable {
        case custom, verified, userCreated = "user_created"
    }
    public var id: String
    public var displayName: String
    public var template: String
    public var status: Status
    public var requiredFields: [String]

    public init(id: String, displayName: String, template: String,
                status: Status = .custom, requiredFields: [String] = ["student_id"]) {
        self.id = id
        self.displayName = displayName
        self.template = template
        self.status = status
        self.requiredFields = requiredFields
    }
}

public enum Presets {
    /// Built-in presets. These are GENERIC patterns — not official university rules.
    public static let builtIn: [NamingPreset] = [
        NamingPreset(id: "custom", displayName: "Custom",
                     template: "{student_id}_{project_title}", status: .custom),
        NamingPreset(id: "id_project", displayName: "ID + Project",
                     template: "{student_id}_{project_title}", status: .custom),
        NamingPreset(id: "id_name_project", displayName: "ID + Student Name + Project",
                     template: "{student_id}_{full_name}_{project_title}",
                     status: .custom,
                     requiredFields: ["student_id", "full_name", "project_title"]),
        NamingPreset(id: "id_module_project", displayName: "ID + Module + Project",
                     template: "{student_id}_{module_code}_{project_title}", status: .custom),
        NamingPreset(id: "surname_id_project", displayName: "Surname + ID + Project",
                     template: "{last_name}_{student_id}_{project_title}", status: .custom),
        NamingPreset(id: "module_id", displayName: "Module + ID",
                     template: "{module_code}_{student_id}", status: .custom),
        NamingPreset(id: "id_surname_assignment", displayName: "ID + Surname + Assignment",
                     template: "{student_id}_{last_name}_{assignment_title}", status: .custom),
        NamingPreset(id: "assignment_candidate_project",
                     displayName: "Assignment code + Candidate + Project",
                     template: "{assignment_code}_{candidate_number}_{project_title}",
                     status: .custom,
                     requiredFields: ["assignment_code", "candidate_number", "project_title"]),
        NamingPreset(id: "group_project", displayName: "Group ID + Project",
                     template: "{group_id}_{project_title}", status: .custom,
                     requiredFields: ["group_id", "project_title"])
    ]

    /// Institution-inspired profiles based on the current Harvard and Chicago
    /// examples reviewed for NITE Submit. They are intentionally labelled
    /// generic: individual departments and assignments may specify a different
    /// convention, which the editable template can accommodate.
    public static let universityProfiles: [NamingPreset] = [
        NamingPreset(id: "custom", displayName: "Generic",
                     template: "{student_id}_{project_title}", status: .custom,
                     requiredFields: ["student_id", "project_title"]),
        NamingPreset(id: "harvard", displayName: "Harvard-style (generic)",
                     template: "{student_id}_{project_title}", status: .custom,
                     requiredFields: ["student_id", "project_title"]),
        NamingPreset(id: "uk_coursework", displayName: "UK coursework (generic)",
                     template: "{module_code}_{student_id}_{project_title}", status: .custom,
                     requiredFields: ["module_code", "student_id", "project_title"]),
        NamingPreset(id: "uk_assignment_code", displayName: "UK assignment code (generic)",
                     template: "{assignment_code}_{student_id}_{project_title}", status: .custom,
                     requiredFields: ["assignment_code", "student_id", "project_title"]),
        NamingPreset(id: "us_coursework", displayName: "US coursework (generic)",
                     template: "{last_name}_{first_name}_{project_title}", status: .custom,
                     requiredFields: ["last_name", "first_name", "project_title"]),
        NamingPreset(id: "us_assignment_code", displayName: "US assignment code (generic)",
                     template: "{last_name}_{assignment_code}", status: .custom,
                     requiredFields: ["last_name", "assignment_code"]),
        NamingPreset(id: "chicago", displayName: "Chicago-style (generic)",
                     template: "{first_name}_{last_name}_{project_title}", status: .custom,
                     requiredFields: ["first_name", "last_name", "project_title"]),
        NamingPreset(id: "id_name_project", displayName: "ID + student name + project (generic)",
                     template: "{student_id}_{full_name}_{project_title}", status: .custom,
                     requiredFields: ["student_id", "full_name", "project_title"]),
        NamingPreset(id: "anonymous_candidate", displayName: "Anonymous candidate number (generic)",
                     template: "{candidate_number}_{project_title}", status: .custom,
                     requiredFields: ["candidate_number", "project_title"])
    ]
}
