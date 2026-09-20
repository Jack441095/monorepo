#pragma once
#include <string>
#include <vector>

// Hard blocklist. The LLM can never override this.
// Mirrored in sidecar/classifier.py::is_blocked — keep in sync.
namespace disksweep {

inline const std::vector<std::string>& BlockedPrefixes() {
  static const std::vector<std::string> v = {
      "/System",
      "/bin",
      "/sbin",
      "/usr",
      "/private/var/vm",
      "/System/Volumes/Data/private/var/vm",
  };
  return v;
}

inline const std::vector<std::string>& BlockedSubstrings() {
  static const std::vector<std::string> v = {
      "Backups.backupdb",
      ".kext/",
      ".kext",
  };
  return v;
}

// Canonicalize `..` and `//` lexically (no filesystem access) so
// "/System/Volumes/Data/../../System" still matches "/System".
inline std::string LexicalNormalise(const std::string& p) {
  std::string out;
  out.reserve(p.size());
  std::vector<std::string> parts;
  std::string cur;
  bool absolute = !p.empty() && p[0] == '/';
  for (size_t i = 0; i <= p.size(); ++i) {
    char c = i < p.size() ? p[i] : '/';
    if (c == '/') {
      if (cur.empty() || cur == ".") {
      } else if (cur == "..") {
        if (!parts.empty()) parts.pop_back();
      } else {
        parts.push_back(cur);
      }
      cur.clear();
    } else {
      cur.push_back(c);
    }
  }
  if (absolute) out = "/";
  for (size_t i = 0; i < parts.size(); ++i) {
    if (i) out += "/";
    out += parts[i];
  }
  return out;
}

inline bool HasPrefixSegment(const std::string& path, const std::string& prefix) {
  if (path.size() < prefix.size()) return false;
  if (path.compare(0, prefix.size(), prefix) != 0) return false;
  // "/Systemx" must NOT match "/System" — require segment boundary.
  if (path.size() == prefix.size()) return true;
  return path[prefix.size()] == '/';
}

// /usr/local caches are the documented exception to the /usr block.
inline bool IsUsrLocalCacheException(const std::string& norm) {
  return HasPrefixSegment(norm, "/usr/local/var/cache") ||
         HasPrefixSegment(norm, "/usr/local/Caches") ||
         norm == "/usr/local/var/cache" || norm == "/usr/local/Caches";
}

inline bool IsBlocked(const std::string& raw_path) {
  std::string norm = LexicalNormalise(raw_path);
  // Exact carve-out first.
  if (IsUsrLocalCacheException(norm)) return false;
  for (const auto& pre : BlockedPrefixes()) {
    if (HasPrefixSegment(norm, pre)) return true;
  }
  for (const auto& sub : BlockedSubstrings()) {
    if (norm.find(sub) != std::string::npos) return true;
  }
  return false;
}

}  // namespace disksweep
