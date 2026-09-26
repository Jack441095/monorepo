# Finishing Phase 1: Jack's list

Phase 1's engineering is done. Three things are left, and they're yours: one test (about 20 minutes), six answers,
and the Developer ID when you're ready to ship.

## 1. Clean-account test (the Phase 1 exit check)

**Pass:** a brand-new Mac user goes from the downloaded DMG to "Live connected, 8 tracks" on the demo set in
**under 15 minutes**, using only the tester guide.

Everything is ready in `/Users/Shared/KENN-clean-account-test/`:
- `KENN-beta-cb9dad5.dmg`, the build testers get, flagged as downloaded so Gatekeeper behaves as it would for them
- `BETA_TESTER_GUIDE.md`, the updated guide (step 2 now says Open Anyway)
- `KENN_Live12_Demo.als`, the demo set

**Before you switch accounts** (the two Lives would fight over the same ports otherwise):
- [ ] Save your work and **quit Live** on your account
- [ ] Tell me "switching", and I'll stop KENN's dev companion. Or run it yourself:
      `zsh /Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/workspace/tmp/kenn-ops/companion.sh stop`

**The test:**
- [ ] System Settings → Users & Groups → **Add User**: Standard account, e.g. "KENN Test"
- [ ] Log in to it (Apple menu → your name → KENN Test). **Start a timer.**
- [ ] Copy the three files from `/Users/Shared/KENN-clean-account-test/` to the Desktop and follow the guide only
- [ ] If Live asks to be authorised on this account, pause the timer for that part (testers will already have it)
- [ ] Open `KENN_Live12_Demo.als` in Live when the guide gets to connecting

Write down the time at each point, and anything you had to guess:

| Point | Time | Stuck on / had to guess |
|---|---|---|
| DMG opened | | |
| KENN opened (after Open Anyway) | | |
| AbletonOSC installed | | |
| AbletonOSC chosen in Live's Control Surface | | |
| Setup shows all three ticks | | |
| KENN answers "How many tracks do I have?" with 8 | | |

**After:**
- [ ] Quit Live, log out of KENN Test, log back in to your account
- [ ] Tell me the times and the notes. I'll fix the guide or setup page wherever you had to guess
- [ ] Delete the KENN Test user whenever you like (Users & Groups). That's yours to do, not mine

Then, tonight, open the demo set on your account and say "ready". I'll start the 8-hour soak.

## 2. Six answers the plan needs from you

Reply in chat. A one-liner each is enough; my recommendation is in brackets.

1. **The beta promise.** Is the "What the beta is" section of the beta plan the scope? [yes, as written]
2. **Testers.** 5 to 10 names; at least 3 with their own real projects.
3. **Two reviewers** for the 100-answer review packet: people who didn't write KENN's answers.
4. **Feedback channel.** [one private Discord channel, plus the diagnostics file for bugs]
5. **Diagnostics.** What may testers' KENN send back? [receipts and timings only, never audio; the "requests KENN
   didn't understand" log only when they tick the box, as built]
6. **Ship the demo set with the beta?** Testers don't get it today, but the guide's examples (kick, snare, hats,
   synth, vocal, drum bus) match it exactly. It's 24 KB and has no audio. [yes, in the DMG, next build]

## 3. Later: sign and notarize

Needs your Apple Developer ID (£79/year). You chose to leave it until just before shipping. Until then, testers use
Open Anyway (step 2 of the guide).
