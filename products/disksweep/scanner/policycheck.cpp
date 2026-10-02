// disksweep-policycheck: asserts policy.hpp blocklist fixtures.
// Exit 0 = all pass, 1 = failure. Wired as ctest.
#include <iostream>
#include <string>
#include <vector>

#include "policy.hpp"

int main() {
  struct Case {
    std::string path;
    bool blocked;
  };
  const std::vector<Case> cases = {
      {"/System/Library/Extensions", true},
      {"/SystemX", false},
      {"/System/Volumes/Data/../../System/Library", true},
      {"/private/var/vm/sleepimage", true},
      {"/Library/Extensions/Fake.kext/Contents", true},
      {"/Library/Extensions/ok.txt", false},
      {"/Volumes/B/Backups.backupdb/x", true},
      {"/usr/local/var/cache/cleanme", false},
      {"/usr/local/Caches/x", false},
      {"/usr/bin/ls", true},
      {"/bin/bash", true},
      {"/sbin/ping", true},
      {"/Users/a/Library/Caches/x", false},
      {"/Users/a/.cache/huggingface/hub/models--x", false},
      {"/usr//local//var/cache//x", false},  // // normalisation
      {"/System/", true},
      {"/system/library", false},  // case-sensitive: lowercase is not the system dir
  };
  // Trash containment for the privileged helper's dst. The traversal
  // case is the 2026-10-02 review finding: the raw prefix check let
  // "$HOME/.Trash/Disksweep/../../../../etc/evil" through and the
  // root helper's fs::rename resolved it to /etc/evil.
  struct TrashCase {
    std::string dst;
    std::string home;
    bool inside;
  };
  const std::vector<TrashCase> trash_cases = {
      {"/Users/a/.Trash/Disksweep/cache.db", "/Users/a", true},
      {"/Users/a/.Trash/Disksweep/../../../../etc/evil", "/Users/a", false},
      // ".." that collapses back inside the trash root stays legal.
      {"/Users/a/.Trash/Disksweep/sub/../../../.Trash/Disksweep/x", "/Users/a",
       true},
      {"/Users/a/.Trash/Disksweep", "/Users/a", true},
      {"/Users/a/.Trash/Disksweepx/evil", "/Users/a", false},
      {"/Users/b/.Trash/Disksweep/x", "/Users/a", false},
      {"/etc/evil", "/Users/a", false},
      {"relative/../../../etc/evil", "/Users/a", false},
  };
  int fails = 0;
  for (const auto& c : cases) {
    bool got = disksweep::IsBlocked(c.path);
    if (got != c.blocked) {
      std::cout << "FAIL " << c.path << " expected=" << c.blocked << " got=" << got << "\n";
      ++fails;
    }
  }
  for (const auto& c : trash_cases) {
    bool got = disksweep::DstInsideTrash(c.dst, c.home);
    if (got != c.inside) {
      std::cout << "FAIL trash dst=" << c.dst << " expected=" << c.inside
                << " got=" << got << "\n";
      ++fails;
    }
  }
  const int total = (int)(cases.size() + trash_cases.size());
  std::cout << (fails ? "FAILURES " : "OK ") << total - fails << "/" << total << "\n";
  return fails ? 1 : 0;
}
