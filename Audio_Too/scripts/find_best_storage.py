#!/usr/bin/env python3
"""Find the best available storage path for Audio_Too cloud data."""

from __future__ import annotations

import shutil
from pathlib import Path

STORAGE_OPTIONS = [
    "/Volumes/Backups_8TB/Audio_Too_Cloud",
    "/Volumes/Jack_Gandy_1TB_SSD/Audio_Too_Cloud",
    "/Volumes/Shenrendao_500GB/Audio_Too_Cloud",
]

def get_best_storage() -> str:
    """Find the first writable storage path with most free space."""
    best = None
    best_free = 0
    
    for path_str in STORAGE_OPTIONS:
        path = Path(path_str)
        try:
            # Check write permission
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            
            # Try to create a test file
            test_file = path / ".space_test"
            test_file.touch()
            test_file.unlink()
            
            # Get free space
            usage = shutil.disk_usage(path)
            if usage.free > best_free:
                best_free = usage.free
                best = path_str
        except (PermissionError, OSError):
            continue
        except Exception:
            continue
    
    return best or "data/cloud"

def main() -> None:
    """Print the best storage path."""
    path = get_best_storage()
    print(path)
    # Also write to a temp file for shell scripts
    Path("/tmp/audiotoo_storage_path.txt").write_text(path)

if __name__ == "__main__":
    main()