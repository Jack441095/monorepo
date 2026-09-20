// Proves the beta gate excludes unsafe files from a sort, using the SAME
// decision function the engine calls. The engine test would need a full scan;
// this pins the contract the engine depends on.
#include "BetaDecisionPolicy.h"
#include <iostream>
#include <vector>
#include <string>

static int failures = 0;
static void check(const char* n, bool c) {
    std::cout << (c ? "  PASS  " : "  FAIL  ") << n << "\n";
    if (!c) ++failures;
}

struct Row { std::string sub; float conf; std::string path; };

int main() {
    using namespace slo;
    std::cout << "beta sort gate:\n";

    // A realistic mixed library slice.
    std::vector<Row> lib = {
        {"Kick",            0.95f, "/lib/Kits/Kick 01.wav"},
        {"Clap",            0.91f, "/lib/Kits/Clap 3.wav"},
        {"Drum Loop",       0.93f, "/lib/Loops/Break 120.wav"},
        {"Percussion",      0.99f, "/lib/Perc/Shaker.wav"},          // must not move
        {"Percussion",      0.55f, "/lib/Perc/Tom_D.wav"},           // must not move
        {"Snare",           0.97f, "/lib/Kits/Snare.wav"},           // suggest only
        {"Foley",           0.88f, "/lib/Foley/door.wav"},           // suggest only
        {"Other/none",      0.90f, "/lib/Misc/weird.wav"},           // review
        {"Kick",            0.20f, "/lib/Kits/maybe_kick.wav"},      // below gate
        {"Kick",            0.99f, "/lib/Impluse Responce/room.wav"},// IR, must not move
        {"Clap",            0.96f, "/lib/Foley/leek_snap.wav"},      // misleading token
    };

    int eligible = 0;
    std::vector<std::string> movedPaths;
    for (const auto& r : lib) {
        const auto slash = r.path.find_last_of('/');
        const std::string name = slash == std::string::npos ? r.path : r.path.substr(slash + 1);
        const auto d = decideBeta(r.sub, r.conf, r.path, name, false, 0.5f);
        if (isEligibleForSort(d)) { ++eligible; movedPaths.push_back(r.path); }
    }

    check("only the proven-safe slice is eligible", eligible == 3);
    bool anyPerc = false, anyIR = false, anySnap = false;
    for (const auto& p : movedPaths) {
        if (p.find("/Perc/") != std::string::npos) anyPerc = true;
        if (isImpulseResponsePath(p)) anyIR = true;
        if (p.find("snap") != std::string::npos) anySnap = true;
    }
    check("no Percussion file would be moved", !anyPerc);
    check("no impulse response would be moved", !anyIR);
    check("no misleading-token file would be moved", !anySnap);
    check("8 of 11 files are left exactly where the user put them",
          (int)lib.size() - eligible == 8);

    // The gate must never widen as confidence rises for an unsafe class.
    bool widened = false;
    for (float c = 0.0f; c <= 1.0f; c += 0.05f)
        widened |= isEligibleForSort(decideBeta("Percussion", c, "/l/p.wav", "p.wav"));
    check("raising confidence never makes Percussion eligible", !widened);

    std::cout << (failures == 0 ? "\nall beta sort gate tests passed\n" : "\nFAILURES\n");
    return failures == 0 ? 0 : 1;
}
