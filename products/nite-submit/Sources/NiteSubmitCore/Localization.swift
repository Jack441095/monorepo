import Foundation

/// Supported interface languages. The current release deliberately uses English
/// labels while keeping the model ready for translated interfaces.
public enum NiteLanguage: String, CaseIterable, Codable, Sendable {
    case english = "en"
    case french = "fr"
    case spanish = "es"
    case german = "de"
    case italian = "it"
    case portuguese = "pt"
    case dutch = "nl"
    case polish = "pl"
    case arabic = "ar"
    case chinese = "zh"
    case japanese = "ja"
    case korean = "ko"
    case hindi = "hi"
    case turkish = "tr"
    case ukrainian = "uk"
    case russian = "ru"
}

public enum NiteLabelKey: String, CaseIterable, Codable, Sendable {
    case studentName = "student_name"
    case studentID = "student_id"
    case candidateNumber = "candidate_number"
    case assignmentCode = "assignment_code"
    case groupID = "group_id"
    case university
    case moduleCode = "module_code"
    case moduleTitle = "module_title"
    case projectTitle = "project_title"
}

public struct NiteLocalization: Sendable {
    public let language: NiteLanguage

    public init(language: NiteLanguage = .english) {
        self.language = language
    }

    public func label(_ key: NiteLabelKey) -> String {
        // Until translated copy is reviewed, every language falls back to the
        // approved English vocabulary. This keeps filenames and field meaning
        // stable while allowing the UI layer to add translations incrementally.
        Self.englishLabels[key, default: key.rawValue]
    }

    public var isEnglishFallback: Bool { language != .english }

    private static let englishLabels: [NiteLabelKey: String] = [
        .studentName: "Student name",
        .studentID: "Student number",
        .candidateNumber: "Candidate number",
        .assignmentCode: "Assignment code",
        .groupID: "Group ID",
        .university: "University",
        .moduleCode: "Module code",
        .moduleTitle: "Module title",
        .projectTitle: "Project title"
    ]
}

public extension MetadataField {
    var localizationKey: NiteLabelKey {
        switch self {
        case .studentName: return .studentName
        case .studentId: return .studentID
        case .candidateNumber: return .candidateNumber
        case .assignmentCode: return .assignmentCode
        case .groupId: return .groupID
        case .university: return .university
        case .moduleCode: return .moduleCode
        case .moduleTitle: return .moduleTitle
        case .projectTitle: return .projectTitle
        }
    }
}
