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

/// Why a scan did not happen. An empty folder is a perfectly good scan result;
/// a folder we could not open is not, and the caller has to be able to tell the
/// two apart instead of reporting "nothing to file" for a library it never read.
public enum FolderScanError: Error, LocalizedError, Sendable {
    case rootMissing(URL)
    case rootNotADirectory(URL)
    case rootUnreadable(URL)

    public var errorDescription: String? {
        switch self {
        case .rootMissing(let url):
            return "“\(url.lastPathComponent)” no longer exists."
        case .rootNotADirectory(let url):
            return "“\(url.lastPathComponent)” is a file, not a folder."
        case .rootUnreadable(let url):
            return "NiteSubmit could not read “\(url.lastPathComponent)”. Check that folder's permissions."
        }
    }
}

/// Recursive scanner for library folder trees.
public struct FolderScanner: Sendable {
    public init() {}

    public func scan(directoryURL: URL, maxDepth: Int = 10, skipHidden: Bool = true) throws -> ScannedFolderManifest {
        let fm = FileManager.default
        var scanned: [ScannedFile] = []
        // enumerator() hands back URLs under a fully resolved root, but the URL we
        // were given can still contain a symlink, and on macOS the temporary
        // directory always does (/var → /private/var). Cutting the relative path
        // out of the path we were handed left a mangled tail like
        // "4DDEA3A4/Alpha.pdf" and inflated the depth count. Foundation will not
        // do this for us: standardizing or resolving the enumerator's own
        // /private/var URL maps it back to /var, so we ask POSIX for the
        // canonical root and keep the given form as a fallback.
        let rootPath = Self.canonicalPath(directoryURL)
        let rootForms = [rootPath, directoryURL.standardizedFileURL.path]

        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: rootPath, isDirectory: &isDirectory) else {
            throw FolderScanError.rootMissing(directoryURL)
        }
        guard isDirectory.boolValue else {
            throw FolderScanError.rootNotADirectory(directoryURL)
        }
        // FileManager.enumerator returns nil both for a path that is not there and
        // for one we may not read, and this code used to turn that nil into an
        // empty manifest. Listing the top level first is what separates "this
        // folder is empty" from "you do not have permission here", so the refusal
        // has to reach the caller instead of looking like a clean scan.
        guard (try? fm.contentsOfDirectory(atPath: rootPath)) != nil else {
            throw FolderScanError.rootUnreadable(directoryURL)
        }
        guard let enumerator = fm.enumerator(
            at: directoryURL,
            includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey, .contentModificationDateKey, .creationDateKey],
            options: skipHidden ? [.skipsHiddenFiles, .skipsPackageDescendants] : [.skipsPackageDescendants]
        ) else {
            throw FolderScanError.rootUnreadable(directoryURL)
        }

        for case let fileURL as URL in enumerator {
            let root = rootForms.first { fileURL.path.hasPrefix($0 + "/") } ?? rootForms[0]
            let relative = String(fileURL.path.dropFirst(root.count + 1))
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

        // Enumeration order is whatever the filesystem hands back, so the same
        // folder produced a different plan from one run to the next and every
        // suffixed name (report_1, report_2 …) landed on a different file each
        // time. Ordinal rather than localized comparison, so a UK and a US
        // machine agree on the plan.
        scanned.sort { $0.relativePath < $1.relativePath }

        return ScannedFolderManifest(rootURL: directoryURL, files: scanned)
    }

    /// realpath(3), falling back to the standardized path when the item does not
    /// exist (the caller is about to report that as a missing root anyway).
    private static func canonicalPath(_ url: URL) -> String {
        guard let resolved = realpath(url.path, nil) else { return url.standardizedFileURL.path }
        defer { free(resolved) }
        return String(cString: resolved)
    }
}
