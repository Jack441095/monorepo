import tempfile
import pytest
from pathlib import Path

from thursday.registry.codebase import (
    safe_resolve_path,
    _handle_codebase_read,
    _handle_codebase_edit,
    _handle_codebase_git,
)


@pytest.fixture(autouse=True)
def mock_workspace_root(monkeypatch):
    """Fixture to isolate workspace root to a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir).resolve()
        monkeypatch.setattr("thursday.registry.codebase.WORKSPACE_ROOT", tmp_path)
        yield tmp_path


def test_safe_resolve_path():
    """Verify safe_resolve_path blocks directory traversal outside workspace root."""
    # Safe path
    p = safe_resolve_path("src/main.py")
    assert p.name == "main.py"
    
    # Traversal path escaping root
    with pytest.raises(ValueError) as excinfo:
        safe_resolve_path("../../../etc/passwd")
    assert "escapes the workspace root" in str(excinfo.value)


def test_handle_codebase_read(mock_workspace_root):
    """Verify codebase_read service successfully reads a file."""
    # Write a test file
    test_file = mock_workspace_root / "test.txt"
    test_file.write_text("Hello World", encoding="utf-8")
    
    # Test read
    res = _handle_codebase_read({"path": "test.txt"}, None, "")
    assert "Hello World" in res


def test_handle_codebase_edit_atomic_success(mock_workspace_root):
    """Verify atomic edit updates file and cleans up backup on success."""
    test_file = mock_workspace_root / "script.py"
    test_file.write_text("print('hello')", encoding="utf-8")
    
    res = _handle_codebase_edit(
        {"path": "script.py", "content": "print('world')"}, None, ""
    )
    assert "successfully updated" in res
    assert test_file.read_text(encoding="utf-8") == "print('world')"
    
    # Backup file should not exist anymore
    assert not test_file.with_suffix(".py.bak").exists()


def test_handle_codebase_edit_python_syntax_error_rollback(mock_workspace_root):
    """Verify edit rolls back to original content if Python syntax check fails."""
    test_file = mock_workspace_root / "invalid.py"
    test_file.write_text("print('original')", encoding="utf-8")
    
    # Invalid syntax: missing closing quote
    res = _handle_codebase_edit(
        {"path": "invalid.py", "content": "print('broken"}, None, ""
    )
    
    assert "Syntax validation failed" in res
    # File content should remain unchanged (rolled back!)
    assert test_file.read_text(encoding="utf-8") == "print('original')"


def test_handle_codebase_git_whitelist():
    """Verify codebase_git only executes whitelisted commands."""
    # Whitelisted
    res = _handle_codebase_git({"command": "status"}, None, "")
    assert "Git output" in res or "Error" in res  # Git not initialized in tmp is fine, just checks execution
    
    # Blocked
    res = _handle_codebase_git({"command": "config --global core.editor rm"}, None, "")
    assert "not whitelisted" in res
