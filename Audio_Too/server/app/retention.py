"""Automated retention policy and cleanup helper for Audio_Too."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

BUSINESS_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BUSINESS_ROOT.parent
UPLOAD_ROOT = BUSINESS_ROOT / "data" / "stem_uploads"
MIX_OUTPUT_ROOT = BUSINESS_ROOT / "data" / "mix_outputs"
LOG_DIR = BUSINESS_ROOT / "data" / "logs"
AUDIO_QUERY_ROOT = BUSINESS_ROOT / "data" / "audio_queries"
MIX_REVIEW_ROOT = REPO_ROOT / "studio" / "agents" / "MixReview" / "data" / "mix_reviews"
DEFAULT_RETENTION_DAYS = 30


def configured_retention_days() -> int:
    """Return the bounded retention period configured for generated files."""
    raw_value = os.getenv("AUDIO_TOO_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_RETENTION_DAYS
    return max(1, min(3650, value))


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def clean_files_older_than(directory: Path, days: int, run: bool = False) -> int:
    if not directory.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    removed_count = 0
    total_bytes = 0

    for item in list(directory.rglob("*")):
        if item.is_file():
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                if mtime < cutoff:
                    size = item.stat().st_size
                    total_bytes += size
                    removed_count += 1
                    if run:
                        item.unlink()
                    else:
                        print(f"[DRY-RUN] Would delete file: {_display_path(item)} ({size / 1024 / 1024:.2f} MB, age: {(datetime.now() - mtime).days} days)")
            except Exception as e:
                print(f"Error accessing {item}: {e}")

    # Clean up empty directories
    if run:
        for root, dirs, files in os.walk(directory, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                except Exception:
                    pass

    if total_bytes > 0:
        label = "Deleted" if run else "Would delete"
        print(f"{label} {removed_count} files totaling {total_bytes / 1024 / 1024:.2f} MB in {_display_path(directory)}")

    return removed_count


def cleanup_expired_mix_outputs(days: int | None = None, *, run: bool = False) -> int:
    """Clean generated automix packages using the configured retention period."""
    keep_days = configured_retention_days() if days is None else max(1, min(3650, int(days)))
    return clean_files_older_than(MIX_OUTPUT_ROOT, keep_days, run)


def run_retention_policy(days: int | None = None, run: bool = False) -> None:
    days = configured_retention_days() if days is None else max(1, min(3650, int(days)))
    print(f"--- Running Retention Policy (Cutoff: {days} days, Run: {run}) ---")

    # 1. Client stem uploads
    clean_files_older_than(UPLOAD_ROOT, days, run)

    # 2. Generated mixes
    cleanup_expired_mix_outputs(days, run=run)

    # 3. MixReview uploads, reports, references
    if MIX_REVIEW_ROOT.exists():
        clean_files_older_than(MIX_REVIEW_ROOT / "uploads", days, run)
        clean_files_older_than(MIX_REVIEW_ROOT / "reports", days, run)
        clean_files_older_than(MIX_REVIEW_ROOT / "references", days * 2, run)

    # 4. Local logs
    clean_files_older_than(LOG_DIR, days, run)

    # 5. Private dashboard audio queries
    clean_files_older_than(AUDIO_QUERY_ROOT, days, run)

    # 6. KENN session DB retention
    try:
        kenn_root = BUSINESS_ROOT.parent / "studio" / "kenn"
        if str(kenn_root) not in sys.path:
            sys.path.insert(0, str(kenn_root))
        from kenn.core.session_memory import delete_old_sessions

        keep_hours = days * 24
        # We can implement or call helper functions if available.
        # Otherwise, query directly.
        if run:
            deleted = delete_old_sessions(keep_hours=keep_hours)
            if deleted > 0:
                print(f"Deleted {deleted} KENN chat sessions older than {keep_hours} hours.")
        else:
            try:
                # KENN uses kenn.db under KENN/chats/kenn.db
                # Let's check session DB connection
                from kenn.core.session_memory import DB_PATH as KENN_DB_PATH
                import sqlite3
                if KENN_DB_PATH.exists():
                    conn_kenn = sqlite3.connect(str(KENN_DB_PATH))
                    cutoff_str = (datetime.now() - timedelta(hours=keep_hours)).strftime("%Y-%m-%d %H:%M:%S")
                    rows = conn_kenn.execute("SELECT id FROM sessions WHERE updated_at < ?", (cutoff_str,)).fetchall()
                    if rows:
                        print(f"[DRY-RUN] Would delete {len(rows)} KENN chat sessions older than {keep_hours} hours.")
                    conn_kenn.close()
            except Exception:
                pass
    except Exception as e:
        print(f"Could not clean KENN sessions: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up old generated files and metadata according to retention policies.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Retention period in days (default: AUDIO_TOO_RETENTION_DAYS or 30)",
    )
    parser.add_argument("--run", action="store_true", help="Opt-in to execute actual deletion (dry-run by default)")
    args = parser.parse_args()

    run_retention_policy(days=args.days, run=args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
