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
  int fails = 0;
  for (const auto& c : cases) {
    bool got = disksweep::IsBlocked(c.path);
    if (got != c.blocked) {
      std::cout << "FAIL " << c.path << " expected=" << c.blocked << " got=" << got << "\n";
      ++fails;
    }
  }
  std::cout << (fails ? "FAILURES " : "OK ") << cases.size() - fails << "/" << cases.size() << "\n";
  return fails ? 1 : 0;
}
