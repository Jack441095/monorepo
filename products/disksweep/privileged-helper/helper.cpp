// Privileged helper: moves ONLY pre-approved paths to Trash.
// Jobs: /Library/* rows the main app cannot move as a standard user.
// Reads JSON lines on stdin: {"src":"...","dst":"..."}.
// Refuses anything the blocklist forbids AND anything whose dst escapes
// ~/.Trash/Disksweep. Links ../scanner/policy.hpp — third enforcement point
// after the C++ scanner note and the Python final guard.
// Install via SMJobBless (see SPEC); never run the scanner as root.
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>

#include "policy.hpp"

namespace fs = std::filesystem;

static bool DstInsideTrash(const std::string& dst) {
  const char* home = std::getenv("HOME");
  std::string trash = std::string(home ? home : "/var/empty") + "/.Trash/Disksweep";
  return dst.size() > trash.size() && dst.compare(0, trash.size(), trash) == 0 &&
         dst[trash.size()] == '/';
}

// Minimal JSON field grabber (helper has no JSON dep by design).
static std::string Field(const std::string& line, const std::string& key) {
  std::string pat = "\"" + key + "\":\"";
  auto i = line.find(pat);
  if (i == std::string::npos) return "";
  i += pat.size();
  std::string out;
  for (; i < line.size(); ++i) {
    char c = line[i];
    if (c == '\\' && i + 1 < line.size()) {
      char n = line[++i];
      out += (n == 'n' ? '\n' : n == 't' ? '\t' : n);
    } else if (c == '"') {
      break;
    } else {
      out += c;
    }
  }
  return out;
}

int main() {
  std::string line;
  int moved = 0, refused = 0;
  while (std::getline(std::cin, line)) {
    std::string src = Field(line, "src"), dst = Field(line, "dst");
    if (src.empty() || dst.empty() || disksweep::IsBlocked(src) || !DstInsideTrash(dst)) {
      std::cerr << "REFUSE " << src << "\n";
      ++refused;
      continue;
    }
    std::error_code ec;
    fs::create_directories(fs::path(dst).parent_path(), ec);
    fs::rename(src, dst, ec);
    if (ec) {
      std::cerr << "FAIL " << src << ": " << ec.message() << "\n";
      ++refused;
    } else {
      ++moved;
    }
  }
  std::cout << "moved=" << moved << " refused=" << refused << "\n";
  return refused ? 2 : 0;
}
