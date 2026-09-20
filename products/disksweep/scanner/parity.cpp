// parity helper: reads paths on stdin, prints 1 (blocked) or 0 per line.
#include <iostream>
#include <string>

#include "policy.hpp"

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    std::cout << (disksweep::IsBlocked(line) ? "1\n" : "0\n");
  }
  return 0;
}
