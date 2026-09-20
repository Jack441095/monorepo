# DiskSweep 1-page manual

WHAT IT DOES: shows what's eating your disk and moves only your approved picks to Trash. Dry run first, always. Everything is local — the AI runs on your Mac via Ollama, nothing uploads.

SAFETY COLORS: SAFE (green, pre-checked) = regenerable caches, logs, installer leftovers — apps rebuild these. REVIEW (yellow) = your models, downloads, old backups, orphan app data — check the box only if you recognize it. BLOCKED (red, locked) = system, kernel and backup paths — never touchable, even by the AI.

UNDO: every Trash run writes an undo log under ~/.Trash/Disksweep/<date>/undo.json. In the app press Undo, or run: python3 -m sidecar.cli --undo --log <undo.json>. Trash auto-keeps the last 10 runs.

COMMON WINS: Xcode DerivedData, Homebrew cache (`brew cleanup` equivalent), npm/pip caches, VS Code C++ index (rebuilds), Spotify/Ableton caches, macOS Aerial videos (turn off in Settings > Wallpaper to stop re-downloads), old iPhone backups (Finder > Manage Backups), unused Ollama/HF models.

NEVER DELETE BY HAND: /System, /Library/Extensions/*.kext, Time Machine folders (Backups.backupdb), ~/Library/Containers for apps you use. DiskSweep blocks these — keep it that way.

NO OLLAMA? Works fine without it — reasons just lack the `llm:` note (rules-only mode, shown in the status bar).
