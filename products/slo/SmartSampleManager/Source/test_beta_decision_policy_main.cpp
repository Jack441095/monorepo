// Safety tests for the beta decision policy. These encode the rules that stop
// SLO moving a user's files on a weak classification.
#include "BetaDecisionPolicy.h"
#include <iostream>
#include <vector>

static int failures = 0;
static void check(const char* name, bool cond) {
    std::cout << (cond ? "  PASS  " : "  FAIL  ") << name << "\n";
    if (!cond) ++failures;
}

int main() {
    using namespace slo;
    std::cout << "beta decision policy:\n";

    auto kick = decideBeta("Kick", 0.95f, "/lib/Kicks/Kick 01.wav", "Kick 01.wav");
    check("Kick above gate is auto-rename eligible",
          kick.action == BetaAction::AutoRenameEligible);
    check("auto-rename eligible still requires approval in beta",
          kick.requiresApproval);

    auto belowRecommended = decideBeta("Kick", 0.90f, "/lib/Kicks/Kick 02.wav", "Kick 02.wav");
    check("the production default gate rejects confidence below 0.93",
          belowRecommended.action == BetaAction::Review);

    auto perc = decideBeta("Percussion", 0.99f, "/lib/P/p.wav", "p.wav");
    check("Percussion NEVER acts, even at 0.99 confidence",
          perc.action == BetaAction::NeverAct);
    check("Percussion is not sort-eligible", !isEligibleForSort(perc));

    auto ir = decideBeta("Kick", 0.99f, "/lib/Impluse Responce/ch.wav", "ch.wav");
    check("impulse response NEVER acts even when classified Kick",
          ir.action == BetaAction::NeverAct);
    check("impulse response is not sort-eligible", !isEligibleForSort(ir));

    auto snap = decideBeta("Clap", 0.95f, "/lib/F/antique_shop_snap.wav",
                           "antique_shop_snap.wav");
    check("misleading token caps at Suggest even when audio agrees",
          snap.action == BetaAction::Suggest);
    check("misleading-token file is not sort-eligible", !isEligibleForSort(snap));

    auto low = decideBeta("Kick", 0.2f, "/lib/K/k.wav", "k.wav");
    check("below gate goes to Review", low.action == BetaAction::Review);
    check("below-gate file is not sort-eligible", !isEligibleForSort(low));

    auto snare = decideBeta("Snare", 0.95f, "/lib/S/s.wav", "s.wav");
    check("Snare is Suggest, not auto-rename", snare.action == BetaAction::Suggest);
    check("Suggest is not sort-eligible", !isEligibleForSort(snare));

    auto other = decideBeta("Other/none", 0.9f, "/lib/x/x.wav", "x.wav");
    check("Other/none goes to Review", other.action == BetaAction::Review);
    check("Other/none asserts no label", other.displayedLabel.empty());

    auto unclass = decideBeta("", 0.9f, "/lib/x/y.wav", "y.wav");
    check("unclassified goes to Review", unclass.action == BetaAction::Review);

    auto usr = decideBeta("Percussion", 0.1f, "/lib/P/p.wav", "p.wav", true);
    check("a user's own label always wins",
          usr.action == BetaAction::AutoRenameEligible && !usr.requiresApproval);

    // Nothing outside the auto-rename tier may ever reach a sort.
    const char* unsafeClasses[] = { "Percussion", "Snare", "Hi-Hat", "Crash",
                                    "Percussion Loop", "Foley", "Other/none" };
    bool anyEligible = false;
    for (const char* c : unsafeClasses)
        anyEligible |= isEligibleForSort(decideBeta(c, 0.99f, "/l/a.wav", "a.wav"));
    check("no unsafe class is EVER sort-eligible at any confidence", !anyEligible);

    std::cout << (failures == 0 ? "\nall beta policy tests passed\n"
                                : "\nFAILURES\n");
    return failures == 0 ? 0 : 1;
}
