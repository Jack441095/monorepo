// DiskSweep read-only scanner (C++17, stdlib only).
// Walks a fixed set of user-accessible roots, never deletes.
// EPERM / missing dirs are skipped gracefully (error_code overloads).
// Emits one JSON object per line matching contracts/scan_item.schema.json.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "policy.hpp"

namespace fs = std::filesystem;

namespace {

std::string JsonEscape(const std::string& s) {
  std::string o;
  for (char c : s) {
    switch (c) {
      case '"': o += "\\\""; break;
      case '\\': o += "\\\\"; break;
      case '\n': o += "\\n"; break;
      case '\t': o += "\\t"; break;
      default:
        if ((unsigned char)c < 0x20) {
          char b[8];
          std::snprintf(b, sizeof b, "\\u%04x", c);
          o += b;
        } else {
          o += c;
        }
    }
  }
  return o;
}

std::string IsoTime(fs::file_time_type t) {
  auto sctp = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
      t - fs::file_time_type::clock::now() + std::chrono::system_clock::now());
  std::time_t tt = std::chrono::system_clock::to_time_t(sctp);
  char buf[32];
  std::strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%S", std::localtime(&tt));
  return buf;
}

std::string Home() {
  const char* h = std::getenv("HOME");
  return h ? h : "/Users/unknown";
}

std::string CategoryFor(const std::string& p) {
  if (p.find("/Caches") != std::string::npos) return "Cache";
  if (p.find("/Logs") != std::string::npos || p.find("/var/log") != std::string::npos) return "Log";
  if (p.find(".Trash") != std::string::npos) return "Trash";
  if (p.find("Downloads") != std::string::npos) return "Downloads";
  if (p.find("huggingface") != std::string::npos || p.find(".ollama") != std::string::npos) return "AIModel";
  if (p.find("Docker") != std::string::npos || p.find("docker") != std::string::npos) return "Docker";
  if (p.find("DerivedData") != std::string::npos || p.find("node_modules") != std::string::npos ||
      p.find(".npm") != std::string::npos || p.find("Homebrew") != std::string::npos ||
      p.find("pip") != std::string::npos)
    return "Dev";
  if (p.find("MobileSync") != std::string::npos || p.find("Application Support") != std::string::npos)
    return "AppSupport";
  return "Other";
}

// Very cheap parent-app hint: basename match against /Applications.
std::string ParentAppOrNull(const std::string& p) {
  auto base = p.substr(p.find_last_of('/') + 1);
  // Strip extensions and version suffixes for a loose match.
  std::error_code ec;
  for (auto it = fs::directory_iterator("/Applications", ec); !ec && it != fs::directory_iterator{}; it.increment(ec)) {
    std::string app = it->path().filename().string();  // "Spotify.app"
    if (app.size() > 4 && app.substr(app.size() - 4) == ".app") app = app.substr(0, app.size() - 4);
    if (base.find(app) != std::string::npos || app.find(base) != std::string::npos) return it->path().string();
  }
  return "";
}

void Emit(const std::string& path, uintmax_t size, std::string mtime, const std::string& cat,
          const std::string& parent, const std::string& sig) {
  std::cout << "{\"path\":\"" << JsonEscape(path) << "\",\"size_bytes\":" << size << ",\"mtime\":\""
            << mtime << "\",\"category\":\"" << cat << "\",\"installed_parent_app_or_null\":"
            << (parent.empty() ? "null" : ("\"" + JsonEscape(parent) + "\"")) << ",\"signature\":\""
            << JsonEscape(sig) << "\"}\n";
}

void Warn(const std::string& msg) { std::cerr << "WARN " << msg << "\n"; }

// Fast path for files >1GB: ask Spotlight (mdfind) instead of walking.
// Targeted stat only; silent fallback to nothing when mdfind is unavailable.
void EmitBigFiles(const std::string& home) {
  const std::string q =
      "mdfind -onlyin " + home + " -onlyin /Applications -onlyin /Library "
      "'kMDItemFSSize > 1000000000' 2>/dev/null";
  FILE* pipe = popen(q.c_str(), "r");
  if (!pipe) return;
  char line[4096];
  int emitted = 0;
  while (fgets(line, sizeof line, pipe) && emitted < 200) {
    std::string p(line);
    while (!p.empty() && (p.back() == '\n' || p.back() == '\r')) p.pop_back();
    if (p.empty() || disksweep::IsBlocked(p)) continue;
    std::error_code ec;
    fs::path fp(p);
    if (!fs::is_regular_file(fp, ec) || ec) continue;
    uintmax_t sz = fs::file_size(fp, ec);
    if (ec || sz < 1000000000ULL) continue;
    std::string mt = IsoTime(fs::last_write_time(fp, ec));
    if (ec) mt = "1970-01-01T00:00:00";
    Emit(p, sz, mt, CategoryFor(p), ParentAppOrNull(p), "kind:file:big");
    ++emitted;
  }
  pclose(pipe);
}

// Spotlight skips caches (~/.cache, ~/.ollama), exactly where multi-GB
// model blobs live. Bounded walk of just those two stores for big files.
void EmitBigFilesInStore(const std::string& store, int max_rows) {
  std::error_code ec;
  if (!fs::exists(store, ec) || ec) return;
  std::vector<std::pair<uintmax_t, std::string>> hits;
  fs::directory_options opts = fs::directory_options::skip_permission_denied;
  for (auto it = fs::recursive_directory_iterator(store, opts, ec);
       !ec && it != fs::recursive_directory_iterator{}; it.increment(ec)) {
    if (ec) break;
    if ((int)it.depth() > 5) {
      it.disable_recursion_pending();
      continue;
    }
    std::error_code e2;
    if (it->is_regular_file(e2) && !e2) {
      uintmax_t sz = it->file_size(e2);
      if (!e2 && sz >= 1000000000ULL) hits.emplace_back(sz, it->path().string());
    }
  }
  std::sort(hits.begin(), hits.end(),
            [](const auto& a, const auto& b) { return a.first > b.first; });
  for (size_t i = 0; i < hits.size() && (int)i < max_rows; ++i) {
    const auto& [sz, p] = hits[i];
    if (disksweep::IsBlocked(p)) continue;
    std::error_code e3;
    std::string mt = IsoTime(fs::last_write_time(fs::path(p), e3));
    if (e3) mt = "1970-01-01T00:00:00";
    Emit(p, sz, mt, "AIModel", "", "kind:file:big");
  }
}

// Emit grandchildren for model stores so the UI gets one row per model
// (HF hub models--* dirs, Ollama models/*). Depth markers in signature
// let the CLI dedupe parent/child sizes instead of double-counting.
uintmax_t DirSize(const fs::path& dir, int max_depth);
void EmitModelBreakdown(const std::string& child) {
  std::string base = child.substr(child.find_last_of('/') + 1);
  if (base != "hub" && base != "models") return;
  std::error_code ec;
  fs::directory_options opts = fs::directory_options::skip_permission_denied;
  for (auto it = fs::directory_iterator(child, opts, ec); !ec && it != fs::directory_iterator{};
       it.increment(ec)) {
    if (ec) break;
    std::string gp = it->path().string();
    std::error_code e2;
    uintmax_t gsz = 0;
    bool is_dir = it->is_directory(e2) && !e2;
    if (is_dir)
      gsz = DirSize(it->path(), 2);
    else if (it->is_regular_file(e2) && !e2)
      gsz = it->file_size(e2);
    std::string gmt = IsoTime(fs::last_write_time(it->path(), e2));
    if (e2) gmt = "1970-01-01T00:00:00";
    Emit(gp, gsz, gmt, "AIModel", "", std::string("kind:") + (is_dir ? "dir" : "file") + ":depth2");
  }
}

uintmax_t DirSize(const fs::path& dir, int max_depth) {
  // Shallow bounded du: depth 3, skip permission errors. Never follows symlinks.
  uintmax_t total = 0;
  std::error_code ec;
  if (max_depth < 0) return 0;
  fs::directory_options opts = fs::directory_options::skip_permission_denied;
  for (auto it = fs::recursive_directory_iterator(dir, opts, ec); !ec && it != fs::recursive_directory_iterator{};
       it.increment(ec)) {
    if (ec) break;
    if ((int)it.depth() > max_depth) {
      it.disable_recursion_pending();
      continue;
    }
    auto sz = it->is_regular_file(ec) ? it->file_size(ec) : 0;
    if (!ec) total += sz;
    if (total > (uintmax_t)50ULL * 1024 * 1024 * 1024) break;  // 50GB cap per root
  }
  return total;
}

}  // namespace

int main() {
  const std::string home = Home();
  // Fixed roots per spec. Full-disk walk is intentionally NOT done here:
  // the sidecar expands only into these roots (least privilege).
  const std::vector<std::string> roots = {
      "/Applications",
      home + "/Downloads",
      home + "/.Trash",
      home + "/Library/Caches",
      home + "/Library/Logs",
      "/Library/Caches",
      "/private/var/log",
      home + "/Library/Application Support",
      home + "/Library/Containers",
      home + "/Library/Group Containers",
      home + "/Library/LaunchAgents",
      "/Library/LaunchAgents",
      "/Library/LaunchDaemons",
      home + "/.cache/huggingface",
      home + "/.ollama",
      home + "/Library/Developer/Xcode/DerivedData",
      home + "/.npm",
      home + "/Library/Caches/Homebrew",
  };
  int skipped = 0;
  for (const auto& r : roots) {
    std::error_code ec;
    fs::path p(r);
    if (!fs::exists(p, ec) || ec) {
      Warn(std::string("skip ") + r + (ec ? (": " + ec.message()) : ": missing"));
      ++skipped;
      continue;
    }  // graceful skip (TCC/EPERM)
    if (disksweep::IsBlocked(r)) {
      Emit(r, 0, "1970-01-01T00:00:00", "Other", "", "blocked");
      continue;
    }
    if (fs::is_directory(p, ec) && !ec) {
      uintmax_t sz = DirSize(p, 3);
      std::string mt = IsoTime(fs::last_write_time(p, ec));
      if (ec) mt = "1970-01-01T00:00:00";
      Emit(r, sz, mt, CategoryFor(r), ParentAppOrNull(r), "kind:dir:depth0");
      // Also emit top-level children (depth 1) so the UI can drill in.
      fs::directory_options opts = fs::directory_options::skip_permission_denied;
      for (auto it = fs::directory_iterator(p, opts, ec); !ec && it != fs::directory_iterator{}; it.increment(ec)) {
        if (ec) break;
        std::string cp = it->path().string();
        uintmax_t csz = 0;
        std::error_code e2;
        bool cdir = it->is_directory(e2) && !e2;
        if (cdir)
          csz = DirSize(it->path(), 2);
        else if (it->is_regular_file(e2) && !e2)
          csz = it->file_size(e2);
        std::string cmt = IsoTime(fs::last_write_time(it->path(), e2));
        if (e2) cmt = "1970-01-01T00:00:00";
        Emit(cp, csz, cmt, CategoryFor(cp), ParentAppOrNull(cp),
             std::string("kind:") + (cdir ? "dir" : "file") + ":depth1");
        if (cdir) EmitModelBreakdown(cp);
      }
    } else if (fs::is_regular_file(p, ec) && !ec) {
      uintmax_t sz = fs::file_size(p, ec);
      if (ec) sz = 0;
      std::string mt = IsoTime(fs::last_write_time(p, ec));
      if (ec) mt = "1970-01-01T00:00:00";
      Emit(r, sz, mt, CategoryFor(r), ParentAppOrNull(r), "kind:file:depth0");
    }
  }
  EmitBigFiles(home);
  EmitBigFilesInStore(home + "/.cache/huggingface/hub", 20);
  EmitBigFilesInStore(home + "/.ollama/models/blobs", 20);
  if (skipped) Warn("skipped roots: " + std::to_string(skipped) + " (Full Disk Access may be off)");
  return 0;
}
