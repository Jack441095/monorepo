# Rolling KENN back, and knowing which build you are on

**Written:** 2026-09-30 · **Task:** E3 · **For:** Jack, and a tester who needs to go back fast

Three things, because "the new build broke" is only recoverable if all three exist.

## 1. Which build am I on?

The menu bar item, bottom of the KENN menu:

```
Build: 65496ca  (2026-09-30, index v-db8c63)
```

That is the short commit, the build date, and the knowledge index the build shipped with. If it reads
`Build: unknown -- no build_manifest.json`, the app was not built by `build_kenn_app.py`, so there is nothing to roll
back to — say so rather than guessing.

Read it **before** filing anything. The commit is the only thing that identifies a build, and a description without it
cannot be reproduced.

## 2. Going back

Every build keeps the **two most recent** `KENN-beta-*.dmg` files in the output folder, so the previous build is
always still installable. Retention is by modification time, not by the commit in the filename, so a rebuild of the
same commit still leaves the pair you actually installed.

1. Quit KENN entirely (menu bar → Quit). Check Activity Monitor or `pgrep -fl kenn` for leftovers.
2. Open the output folder and find the `KENN-beta-<commit>.dmg` before the current one.
3. Drag **KENN.app** to Applications, choosing *Replace*.
4. Start KENN and check the menu again: the commit should be the older one.
5. The knowledge index is **not** rolled back by this. A build ships its own index inside `Contents/Resources`, so
   installing the older app restores that build's index too. Nothing outside `KENN.app` is touched, so no set, no
   preset and no Live project is affected by a rollback.

If the older build will not start, the failure is almost always the **data folder**, not the app: check that
`Contents/Resources/data/index/CURRENT` names a version whose folder exists. A half-copied copy of the app is the
usual cause, and re-copying fixes it.

## What a rollback does **not** undo

Worth being blunt about, because a rollback that looks complete and is not wastes an evening:

- **Data KENN wrote.** Receipts, the asked log and project memory live outside the app bundle and survive a
  rollback. That is deliberate — a producer's preferences should not vanish because a build was bad — but it means a
  rollback is not a clean slate.
- **Remote Scripts.** `Contents/Resources/kenn/integrations/ableton-osc` is copied per app, so an older app's AbletonOSC
  comes back with it. Check the version if the bridge misbehaves after a rollback.
- **Anything in a set.** KENN never writes to a Live set on its own initiative; every write went through Apply. A
  rollback cannot undo a change already applied to a set, which is what undo is for.

## Before shipping a build that might need rolling back

- Run it yourself for a day first. The soak is the gate, not the build succeeding.
- Record the receipts and the commit in the release note, so the two DMGs in the output folder can be told apart.
- If the build was **signed**, the older DMG was signed too and both keep their signatures. A build signed with a
  different Developer ID will not replace one signed with another; that is Gatekeeper, and `xattr -dr com.apple.quarantine`
  on the app clears a quarantined copy but does not bypass a signature mismatch.