from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose startup + console logs (prints full command cheat-sheet and diagnostics).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Quiet console (errors only). File logs still capture full detail.",
    )
    parser.add_argument(
        "--mode",
        choices=("generative", "offline"),
        default=None,
        help="Startup mode override: generative or offline (skips interactive prompt).",
    )
    # Preset family discovery (lists and exits early).
    parser.add_argument("--list-preset-families", action="store_true", help="List all preset families and exit.")
    parser.add_argument("--list-meta-presets", action="store_true", help="List local meta presets (.audiogen/presets) and exit.")
    parser.add_argument("--list-packs", action="store_true", help="List available sample packs and exit.")
    parser.add_argument("--list-styles", action="store_true", help="List available style profiles and exit.")
    parser.add_argument("--list-style-architectures", action="store_true", help="List available style-architecture macro presets and exit.")
    parser.add_argument("--list-fx", action="store_true", help="List available FX presets and exit.")
    parser.add_argument("--list-arrangements", action="store_true", help="List available arrangement modes and exit.")
    parser.add_argument("--list-producer-macros", action="store_true", help="List available producer macros and exit.")

    parser.add_argument("--preset", help="Meta preset name in .audiogen/presets (without .json)")
    parser.add_argument("--pack", help="Sample pack name (overrides preset)")
    parser.add_argument("--style", help="Style profile name (overrides preset)")
    parser.add_argument("--style-architecture", help="Style architecture macro name (applies on top of style profile/preset).")
    parser.add_argument("--fx", help="FX preset name (overrides preset)")
    parser.add_argument("--arrangement", help="Arrangement style/mode (overrides preset)")
    parser.add_argument(
        "--arrangement-form",
        default=None,
        help=(
            "Arrangement form for arranged songs (alias of --arrangement). "
            "Examples: default | dialogue (call and responce) WIP | swing."
        ),
    )
    parser.add_argument(
        "--producer-macro",
        action="append",
        default=None,
        help="Producer macro to apply (repeatable): cinematic | club | intimate | narrative.",
    )
    parser.add_argument(
        "--producer-macro-amount",
        type=float,
        default=1.0,
        help="Amount for --producer-macro applications (0..1, default 1.0).",
    )
    parser.add_argument(
        "--narrative-macro",
        action="store_true",
        help="Enable the dedicated song-level narrative macro upgrades.",
    )
    parser.add_argument(
        "--narrative-macro-amount",
        type=float,
        default=1.0,
        help="Amount for --narrative-macro (0..1, default 1.0).",
    )
    parser.add_argument(
        "--transition-bars",
        type=int,
        default=None,
        help="Manual emotion switch boundary in heard bars (higher = smoother; default: config).",
    )
    parser.add_argument(
        "--blend-bars",
        type=int,
        default=None,
        help="Musical morph: blend first N bars of targets after emotion switch (0 disables; default: config).",
    )
    parser.add_argument(
        "--handoff-fade-scale",
        type=float,
        default=None,
        help="Emotion handoff audio crossfade scale (0.12..1.0; default: config).",
    )
    parser.add_argument(
        "--handoff-fade-max",
        type=float,
        default=None,
        help="Emotion handoff audio crossfade max seconds (0.04..2.5; default: config).",
    )
    parser.add_argument(
        "--hook-safe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable hook-safe composition tuning (stronger hooks, lower randomness). Default: enabled.",
    )
    parser.add_argument(
        "--melody-staged-experimental",
        action="store_true",
        help="Enable staged Markov melody bundle (rhythm–pitch coupling, joint rerank, breath biases).",
    )
    parser.add_argument(
        "--variety",
        type=float,
        default=1.0,
        help="Variety amount (0..1). Higher loosens arp/motif locks and enables novelty selection. Default: 1.0.",
    )
    parser.add_argument(
        "--arp-octave-reach",
        action="store_true",
        help=(
            "Allow occasional ±12 semitone arp steps (Ableton-style lift). "
            "Default composition config keeps this off for a strict single-voice arp bed."
        ),
    )
    parser.add_argument(
        "--note-log",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable per-note `.log` auditing to CONFIG.composition.note_log_path (default: follow config/preset).",
    )
    parser.add_argument(
        "--note-log-path",
        default=None,
        help="Override note log output path (file or directory). Default: logs/notes.log",
    )
    parser.add_argument(
        "--note-log-console",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print a compact generated-notes dump into logs/runtime.log (noisy; default: off).",
    )
    parser.add_argument(
        "--log-only",
        action="store_true",
        help=(
            "Generate a short arranged preview and write note logs, then exit (no realtime audio playback). "
            "Uses --emotion/--root/--arrangement-form (or config defaults)."
        ),
    )
    parser.add_argument(
        "--log-only-preview-sections",
        type=int,
        default=2,
        help="For --log-only: number of sections to generate for the preview (default: 2).",
    )
    parser.add_argument(
        "--sampler-debug-log",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable plain-text per-bar sampler workload log (CONFIG.audio.sampler_debug_log_path). Default: follow preset.",
    )
    parser.add_argument(
        "--sampler-debug-log-path",
        default=None,
        help="Override sampler debug log path (default: logs/debug/sampler.log).",
    )
    parser.add_argument(
        "--mixer-master-debug-log",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable plain-text per-bar mixer strips + master bus snapshot log.",
    )
    parser.add_argument(
        "--mixer-master-debug-log-path",
        default=None,
        help="Override mixer/master debug log path (default: logs/debug/mixer_master.log).",
    )
    parser.add_argument(
        "--fresh-on-start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reseed and reset song memory right after startup (extra insurance against repeats). Default: enabled.",
    )
    parser.add_argument(
        "--reseed-every-generation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Before each generated section/song from main (AdapterComposer), roll a new RNG seed "
            "and reset arrangement memory (default: on). Disable with --no-reseed-every-generation."
        ),
    )
    parser.add_argument(
        "--export-live-melody-training",
        action="store_true",
        help="Append generated melodies to JSONL for Markov retraining (see composition config path).",
    )
    parser.add_argument(
        "--export-live-melody-training-path",
        default=None,
        help="Override JSONL path for --export-live-melody-training.",
    )
    parser.add_argument(
        "--offline-export-dir",
        default="songs",
        help="Export directory for offline outputs (default: songs).",
    )
    parser.add_argument(
        "--offline-export-prefix",
        default="song",
        help="Filename prefix for offline exports (default: song).",
    )
    parser.add_argument(
        "--offline-emotion",
        default="neutral",
        help="Default emotion for offline export (name). For batch runs you can pass a comma-separated list to cycle.",
    )
    parser.add_argument(
        "--offline-count",
        type=int,
        default=0,
        help="Offline batch: number of songs to render then exit. 0 = interactive (TTY) or one-shot (non-TTY).",
    )
    parser.add_argument(
        "--offline-outputs",
        default="wav,midi",
        help="Comma-separated offline outputs: wav,midi,report,meta. Also accepts: all, none. Default: wav,midi.",
    )
    parser.add_argument(
        "--offline-arrangement-form",
        default=None,
        help="Offline-only arrangement form override (default/dialogue (call and responce) WIP/swing).",
    )
    parser.add_argument(
        "--offline-arranged-seconds",
        type=float,
        default=None,
        help="Offline-only target arranged seconds (overrides composition.arranged_song_seconds).",
    )
    parser.add_argument(
        "--offline-arranged-max-bars",
        type=int,
        default=None,
        help="Offline-only max bars cap for arranged songs (overrides composition.arranged_song_max_bars).",
    )
    parser.add_argument(
        "--offline-arranged-bars-per-section",
        type=int,
        default=None,
        help="Offline-only bars-per-section for arranged forms (overrides composition.bars_per_section).",
    )
    parser.add_argument(
        "--offline-train",
        choices=("none", "markov", "logit", "dataset", "all"),
        default="none",
        help="Run offline training and exit: markov, logit residual, dataset export/validation, or all.",
    )
    parser.add_argument(
        "--offline-train-tag",
        default="",
        help="Tag for offline training outputs (used as folder/file prefix).",
    )
    parser.add_argument(
        "--offline-train-dir",
        default=".cache/offline_training",
        help="Base directory for tagged offline training outputs.",
    )
    parser.add_argument(
        "--offline-train-jsonl",
        default=".cache/live_melody_training.jsonl",
        help="Input melody training JSONL for offline markov/logit training.",
    )
    parser.add_argument("--offline-train-min-notes", type=int, default=4)
    parser.add_argument("--offline-train-min-accept", type=float, default=0.0)
    parser.add_argument("--offline-train-min-lines", type=int, default=1)
    parser.add_argument("--offline-train-max-rest-rate", type=float, default=0.55)
    parser.add_argument("--offline-train-min-emotions", type=int, default=0)
    parser.add_argument("--offline-train-min-section-roles", type=int, default=0)
    parser.add_argument("--offline-train-max-emotion-share", type=float, default=1.0)
    parser.add_argument(
        "--offline-train-require-metadata",
        action="store_true",
        help="Require emotion/phrase/chord metadata in the JSONL eval gate.",
    )
    parser.add_argument(
        "--offline-train-skip-eval",
        action="store_true",
        help="Skip JSONL eval gate before offline training.",
    )
    parser.add_argument(
        "--offline-train-dedup",
        action="store_true",
        help="Deduplicate melody rows before Markov retraining.",
    )
    parser.add_argument(
        "--offline-train-grouped",
        choices=("none", "emotion", "family", "both"),
        default="both",
        help="Grouped Markov training mode for --offline-train markov/all.",
    )
    parser.add_argument("--offline-train-min-group-melodies", type=int, default=8)
    parser.add_argument("--offline-train-seed", type=int, default=0)
    parser.add_argument("--offline-train-logit-order", type=int, default=6)
    parser.add_argument("--offline-train-logit-ridge", type=float, default=1e-2)
    parser.add_argument(
        "--offline-promote-run",
        default="",
        help="Promote artifacts from an offline training run directory and exit.",
    )
    parser.add_argument(
        "--offline-promote-manifest",
        default="",
        help="Optional offline training manifest path/name for --offline-promote-run.",
    )
    parser.add_argument(
        "--offline-promote-kind",
        choices=("markov", "logit", "all"),
        default="all",
        help="Artifact kind to promote from the offline run.",
    )
    parser.add_argument(
        "--offline-promote-dir",
        default="training_data/active_models",
        help="Destination directory for promoted active models.",
    )
    parser.add_argument(
        "--offline-promote-dry-run",
        action="store_true",
        help="Print promotion plan without copying artifacts.",
    )
    parser.add_argument(
        "--melody-retrained-markov",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Load retrained melody MarkovModelSet (.pkl) at startup. Default-on in config; "
             "pass --no-melody-retrained-markov to force the faster untrained melody path.",
    )
    parser.add_argument(
        "--melody-retrained-markov-path",
        default=None,
        help="Path to .pkl from scripts/melody_jsonl_retrain.py.",
    )
    parser.add_argument(
        "--melody-retrained-markov-hot-reload",
        action="store_true",
        help="Hot-reload retrained melody Markov .pkl by file mtime during runtime.",
    )
    parser.add_argument(
        "--melody-retrained-markov-hot-reload-interval",
        type=float,
        default=None,
        help="Seconds between retrained melody Markov hot-reload checks.",
    )
    parser.add_argument(
        "--melody-neural-logit-residual",
        action="store_true",
        help="Enable Phase-2d linear logit residual on interval sampling (requires weights path).",
    )
    parser.add_argument(
        "--melody-neural-logit-residual-path",
        default=None,
        help="Path to .npz from scripts/train_melody_logit_residual.py.",
    )
    parser.add_argument(
        "--replay-chords",
        action="store_true",
        help=(
            "Pick a random chord progression from the emotion/role pool in data/music_data.py, "
            "tile it to each section, and skip the chord Markov walk (melody/arp follow that harmony)."
        ),
    )
    parser.add_argument(
        "--chorus-ref-wavs",
        action="store_true",
        help="Enable chorus-only arp overrides from .cache/tuning_suggestions.json.",
    )
    parser.add_argument(
        "--chorus-ref-wavs-path",
        default=None,
        help="Path to tuning suggestions JSON (default: .cache/tuning_suggestions.json).",
    )
    parser.add_argument(
        "--chorus-ref-strength",
        type=float,
        default=None,
        help="Blend strength for chorus reference arp overrides (0..1).",
    )
    parser.add_argument(
        "--chorus-ref-target-boost",
        type=float,
        default=None,
        help="Multiplier for reference target-notes-per-bar before blending (chorus-only).",
    )
    parser.add_argument(
        "--chorus-ref-melody",
        action="store_true",
        help="Enable chorus-only melody overrides from .cache/tuning_suggestions.json.",
    )
    parser.add_argument(
        "--chorus-ref-melody-path",
        default=None,
        help="Path to melody tuning suggestions JSON (default: .cache/tuning_suggestions.json).",
    )
    parser.add_argument(
        "--chorus-ref-melody-strength",
        type=float,
        default=None,
        help="Blend strength for chorus melody reference overrides (0..1).",
    )
    parser.add_argument(
        "--chorus-ref-melody-target-boost",
        type=float,
        default=None,
        help="Multiplier for chorus melody notes-per-bar references before blending.",
    )
    parser.add_argument(
        "--preset-launch-seed",
        action="store_true",
        help=(
            "When set, use composition.seed from preset/config if provided; otherwise random. "
            "Without this flag: random launch seed each run unless "
            "CONFIG.composition.generative_random_launch_seed_default is False and a seed is set."
        ),
    )
    parser.add_argument(
        "--drums",
        choices=("auto", "on", "off"),
        default="auto",
        help=(
            "Chorus 4/4 kick + sidechain ducking: auto=prompt when interactive (TTY), "
            "on=full kick+sidechain, off=no kick and no sidechain."
        ),
    )
    parser.add_argument(
        "--emotion",
        default="neutral",
        help="Start emotion name (default: neutral)",
    )
    parser.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60)")
    parser.add_argument(
        "--performance",
        # Primary interface is now two modes: high vs low CPU.
        # Keep legacy strings accepted so old scripts/presets don't break.
        choices=("high", "low", "quality", "balanced", "maximum"),
        default="high",
        help="Audio engine profile: high (richer, higher CPU) or low (fastest/lowest CPU). Legacy: quality/balanced/maximum.",
    )
    return parser

