import os
import sys
import sqlite3
import pytest
from pathlib import Path
from server.app import db

def test_database_safety_guards(tmp_path, monkeypatch):
    real_db_path = (db.REPO_ROOT / "data" / "audio_too.db").resolve()
    
    # Force test-process mode detection in db.py to test the guard logic
    monkeypatch.setattr(db, "is_in_test_process", lambda: True)
    
    # 1. production-like / business DB path -> REJECT
    monkeypatch.setattr(db, "DB_PATH", real_db_path)
    with pytest.raises(PermissionError, match="rejected on production-like path"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=False)
        
    # Relative-path confusion -> REJECT
    monkeypatch.setattr(db, "DB_PATH", Path("data/audio_too.db"))
    with pytest.raises(PermissionError, match="rejected on production-like path"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=False)
        
    # Symlink/path alias toward protected DB -> REJECT
    symlink_path = tmp_path / "symlink_to_prod.db"
    if not symlink_path.exists():
        try:
            os.symlink(real_db_path, symlink_path)
            monkeypatch.setattr(db, "DB_PATH", symlink_path)
            with pytest.raises(PermissionError, match="rejected on production-like path"):
                db.assert_safe_db_for_migration_or_rollback(is_destructive=False)
        except OSError:
            # Skip if OS does not support symlinks in this environment
            pass

    # 2. Unknown DB / not in temporary directory -> REJECT
    monkeypatch.setattr(db, "DB_PATH", Path("/usr/local/var/some_other_db.db"))
    with pytest.raises(PermissionError, match="not in a temporary test directory"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=False)

    # 3. Missing marker -> REJECT (for destructive)
    test_db_path = tmp_path / "test_missing_marker.db"
    # Create the empty DB file
    test_db_path.touch()
    
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    with pytest.raises(PermissionError, match="lacks required test marker"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=True)

    # 4. Wrong marker -> REJECT
    wrong_marker_file = test_db_path.with_suffix(".test_marker")
    wrong_marker_file.write_text("NOT_THE_CORRECT_PREFIX_123")
    with pytest.raises(PermissionError, match="Invalid test marker content"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=True)

    # 5. Temporary test DB with correct marker -> ALLOW
    db.create_test_marker(test_db_path)
    db.assert_safe_db_for_migration_or_rollback(is_destructive=True)  # Should not raise

    # 6. Copied real DB without test marker -> REJECT
    copied_db_path = tmp_path / "copied_real.db"
    # Create a non-empty DB file resembling a copied real DB
    with sqlite3.connect(copied_db_path) as conn:
        conn.execute("CREATE TABLE dummy (id INT)")
        conn.commit()
    # It exists and st_size > 0, and has no marker file or metadata table
    monkeypatch.setattr(db, "DB_PATH", copied_db_path)
    with pytest.raises(PermissionError, match="Database lacks required test marker"):
        db.assert_safe_db_for_migration_or_rollback(is_destructive=True)
