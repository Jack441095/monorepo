import Foundation

/// File categories for library folder organization.
public enum FileCategory: String, Codable, CaseIterable, Sendable {
    case documents
    case images
    case audio
    case video
    case archives
    case code
    case other

    public var folderName: String {
        switch self {
        case .documents: return "Documents"
        case .images: return "Images"
        case .audio: return "Audio"
        case .video: return "Video"
        case .archives: return "Archives"
        case .code: return "Code"
        case .other: return "Other"
        }
    }

    public static func categorize(extension ext: String) -> FileCategory {
        let e = ext.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        switch e {
        case "pdf", "docx", "doc", "pages", "txt", "rtf", "odt", "csv", "xlsx", "pptx", "md":
            return .documents
        case "jpg", "jpeg", "png", "heic", "gif", "svg", "webp", "tiff", "bmp", "raw", "cr2", "nef":
            return .images
        case "mp3", "wav", "flac", "aac", "m4a", "ogg", "aiff", "wma":
            return .audio
        case "mp4", "mov", "avi", "mkv", "webm", "flv", "m4v", "wmv":
            return .video
        case "zip", "7z", "tar", "gz", "bz2", "xz", "rar", "dmg", "pkg":
            return .archives
        case "swift", "py", "js", "ts", "cpp", "c", "h", "java", "go", "rs", "html", "css", "json", "sh":
            return .code
        default:
            return .other
        }
    }
}

/// Metadata for a scanned file within a library folder.
public struct ScannedFile: Codable, Equatable, Sendable {
    public var url: URL
    public var relativePath: String
    public var category: FileCategory
    public var extensionName: String
    public var sizeBytes: Int64
    public var modifiedDate: Date?
    public var createdDate: Date?

    public init(url: URL, relativePath: String, category: FileCategory,
                extensionName: String, sizeBytes: Int64,
                modifiedDate: Date? = nil, createdDate: Date? = nil) {
        self.url = url
        self.relativePath = relativePath
        self.category = category
        self.extensionName = extensionName
        self.sizeBytes = sizeBytes
        self.modifiedDate = modifiedDate
        self.createdDate = createdDate
    }
}

/// Result of scanning a folder structure.
public struct ScannedFolderManifest: Codable, Equatable, Sendable {
    public var rootURL: URL
    public var totalFiles: Int
    public var totalSizeBytes: Int64
    public var files: [ScannedFile]

    public init(rootURL: URL, files: [ScannedFile]) {
        self.rootURL = rootURL
        self.files = files
        self.totalFiles = files.count
        self.totalSizeBytes = files.reduce(0) { $0 + $1.sizeBytes }
    }
}

/// Recursive scanner for library folder trees.
public struct FolderScanner: Sendable {
    public init() {}

    public func scan(directoryURL: URL, maxDepth: Int = 10, skipHidden: Bool = true) throws -> ScannedFolderManifest {
        let fm = FileManager.default
        var scanned: [ScannedFile] = []
        let rootPath = directoryURL.path

        guard let enumerator = fm.enumerator(
            at: directoryURL,
            includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey, .creationDateKey],
            options: skipHidden ? [.skipsHiddenFiles, .skipsPackageDescendants] : [.skipsPackageDescendants]
        ) else {
            return ScannedFolderManifest(rootURL: directoryURL, files: [])
        }

        for case let fileURL as URL in enumerator {
            let relative = String(fileURL.path.dropFirst(rootPath.count)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            let depth = relative.components(separatedBy: "/").count
            if depth > maxDepth { continue }

            let resourceValues = try? fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey, .creationDateKey])
            guard resourceValues?.isRegularFile == true else { continue }

            let ext = fileURL.pathExtension
            let category = FileCategory.categorize(extension: ext)
            let size = Int64(resourceValues?.fileSize ?? 0)
            let modDate = resourceValues?.contentModificationDate
            let createDate = resourceValues?.creationDate

            let scannedFile = ScannedFile(
                url: fileURL,
                relativePath: relative,
                category: category,
                extensionName: ext,
                sizeBytes: size,
                modifiedDate: modDate,
                createdDate: createDate
            )
            scanned.append(scannedFile)
        }

        return ScannedFolderManifest(rootURL: directoryURL, files: scanned)
    }
}
