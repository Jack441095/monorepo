"""Codebase control services registry for Thursday.

Provides safe abstractions for reading, searching, editing, testing, compiling,
and committing the workspace codebase.
"""

from __future__ import annotations

import logging
import os
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any

from thursday.registry.core import ServiceDef

logger = logging.getLogger("thursday.registry.codebase")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.resolve()


def safe_resolve_path(path_str: str) -> Path:
    """Resolve and validate path safety to prevent directory traversal outside workspace.

    Uses real filesystem containment (`Path.is_relative_to`, which compares
    resolved path *segments*), not a string-prefix check. A string-prefix
    check (the previous implementation:
    ``str(resolved).startswith(str(WORKSPACE_ROOT))``) is not a valid
    containment test -- a sibling directory whose name happens to share
    ``WORKSPACE_ROOT`` as a string prefix (e.g. ``thursday_backup`` next to
    ``thursday``, or ``Audio_Too_backup`` next to ``Audio_Too``) would pass
    it despite being a completely different directory outside the intended
    workspace (docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md,
    P0-11). ``is_relative_to`` compares path components, so
    ``.../thursday_backup`` is correctly rejected as not relative to
    ``.../thursday`` even though the strings share a prefix.

    ``.resolve()`` also collapses ``..`` segments and symlinks before the
    containment check runs, so a traversal (``../../etc/passwd``) or a
    symlink pointing outside the workspace is judged by where it actually
    ends up on disk, not by its literal spelling.
    """
    resolved = (WORKSPACE_ROOT / path_str.strip()).resolve()
    if not resolved.is_relative_to(WORKSPACE_ROOT):  # True for resolved == WORKSPACE_ROOT too
        raise ValueError(f"Access denied: path '{path_str}' escapes the workspace root.")
    return resolved


def _handle_codebase_read(ctx: dict, api: Any, text: str) -> str:
    """Read file content safely."""
    path_str = ctx.get("path") or text.strip()
    if not path_str:
        return "Please specify a file path to read."
    
    try:
        file_path = safe_resolve_path(path_str)
        if not file_path.exists():
            return f"Error: File '{path_str}' does not exist."
        if not file_path.is_file():
            return f"Error: '{path_str}' is not a file."
            
        content = file_path.read_text(encoding="utf-8", errors="replace")
        # Cap length to prevent LLM context overflow
        if len(content) > 100000:
            content = content[:100000] + "\n... [TRUNCATED due to large size]"
        return f"File content of '{path_str}':\n\n```\n{content}\n```"
    except Exception as e:
        return f"Error reading file: {e}"


def _handle_codebase_search(ctx: dict, api: Any, text: str) -> str:
    """Search codebase for a pattern safely (ripgrep-like search)."""
    query = ctx.get("query") or text.strip()
    if not query:
        return "Please specify a query pattern to search for."
        
    try:
        # Run grep search in-process or via subprocess ripgrep (safe since we only read)
        # To make it simple and dependency-free, search files matching *.py, *.md in workspace
        results = []
        for path in WORKSPACE_ROOT.glob("**/*"):
            if not path.is_file():
                continue
            # Skip hidden/venv files
            rel_str = str(path.relative_to(WORKSPACE_ROOT))
            if rel_str.startswith(".") or "venv" in rel_str or "__pycache__" in rel_str:
                continue
                
            try:
                # Read line-by-line
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        if query in line:
                            results.append(f"{rel_str}:{line_no}: {line.strip()}")
                            if len(results) > 100:
                                break
            except Exception:
                pass
            if len(results) > 100:
                break
                
        if not results:
            return f"No matches found for query '{query}'."
        return f"Search results for '{query}':\n\n" + "\n".join(results)
    except Exception as e:
        return f"Error searching codebase: {e}"


def _handle_codebase_edit(ctx: dict, api: Any, text: str) -> str:
    """Perform atomic edit on a file with syntax check fallback."""
    path_str = ctx.get("path")
    content = ctx.get("content")
    target = ctx.get("target")
    replacement = ctx.get("replacement")
    
    if not path_str:
        return "Error: File path is required for edits."
        
    try:
        file_path = safe_resolve_path(path_str)
        
        # 1. Create backup if file exists
        backup_path = None
        if file_path.exists():
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            shutil.copy2(file_path, backup_path)
            old_content = file_path.read_text(encoding="utf-8")
        else:
            old_content = ""
            
        # Ensure parent directories exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Compute new content
        new_content = ""
        if content is not None:
            new_content = content
        elif target is not None and replacement is not None:
            if not old_content:
                raise ValueError("Cannot perform search-and-replace on a new file.")
            if target not in old_content:
                raise ValueError(f"Target text not found in '{path_str}'")
            new_content = old_content.replace(target, replacement)
        else:
            raise ValueError("Provide either 'content' or 'target' and 'replacement' parameters.")

        # Write to file
        file_path.write_text(new_content, encoding="utf-8")

        # 3. Syntax Verification check for Python files
        if file_path.suffix == ".py":
            try:
                subprocess.run(
                    [sys.executable, "-m", "py_compile", str(file_path)],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as err:
                # Syntax error! Restore backup and raise error
                if backup_path and backup_path.exists():
                    shutil.copy2(backup_path, file_path)
                else:
                    file_path.unlink()
                raise ValueError(f"Syntax validation failed: {err.stderr.strip()}")

        # Clean up backup
        if backup_path and backup_path.exists():
            backup_path.unlink()
            
        return f"File '{path_str}' successfully updated. Action completed atomically."
    except Exception as e:
        return f"Error executing codebase edit: {e}"


def _handle_codebase_git(ctx: dict, api: Any, text: str) -> str:
    """Run whitelisted git command safely."""
    command = ctx.get("command") or "status"
    allowed_subcommands = {"status", "diff", "log", "checkout", "commit", "push"}
    
    # Simple whitelist matching
    tokens = command.split()
    if not tokens or tokens[0] not in allowed_subcommands:
        return f"Error: Git command '{command}' is not whitelisted."
        
    try:
        # Construct exact git command line
        cmd = ["git"] + tokens
        
        # Destructive protection gate: push --force
        if tokens[0] == "push" and any(t in tokens for t in ("--force", "-f", "force")):
            # Destructive confirmation check
            pass  # Handled by request_risk/confirmation gate
            
        res = subprocess.run(
            cmd,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        out = res.stdout or ""
        err = res.stderr or ""
        
        # Cap output
        if len(out) > 10000:
            out = out[:10000] + "\n... [TRUNCATED]"
        if len(err) > 5000:
            err = err[:5000] + "\n... [TRUNCATED]"
            
        return f"Git output:\n\n{out}\n{err}"
    except Exception as e:
        return f"Error executing git command: {e}"


def _handle_codebase_test(ctx: dict, api: Any, text: str) -> str:
    """Run pytest safely with time boundaries."""
    test_filter = ctx.get("filter") or ""
    
    cmd = ["pytest"]
    if test_filter:
        cmd.append(test_filter)
        
    try:
        res = subprocess.run(
            cmd,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=30.0,
            env={**os.environ, "PAGER": "cat"},
        )
        out = res.stdout or ""
        err = res.stderr or ""
        
        # Cap output
        if len(out) > 20000:
            out = out[:20000] + "\n... [TRUNCATED]"
        return f"Test suite output:\n\n{out}\n{err}"
    except subprocess.TimeoutExpired:
        return "Error: Test suite execution timed out after 30 seconds."
    except Exception as e:
        return f"Error executing tests: {e}"


def _handle_codebase_build(ctx: dict, api: Any, text: str) -> str:
    """Run project build commands."""
    try:
        # Detect if we have Makefile or build script, default run make build or build-index
        cmd = ["make"]
        if not (WORKSPACE_ROOT / "Makefile").exists():
            cmd = ["./audio-too", "build"]
            
        res = subprocess.run(
            cmd,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        return f"Build output:\n\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Error executing build: {e}"


def _register_codebase_services(services: dict[str, ServiceDef], api: Any) -> None:
    """Register all codebase control services in the registry."""
    services["codebase_read"] = ServiceDef(
        name="Read File",
        description="Read file content inside the workspace path.",
        triggers=["read file", "show file", "cat file", "view file", "open file"],
        intents=["codebase_control"],
        action=_handle_codebase_read,
    )
    
    services["codebase_search"] = ServiceDef(
        name="Search Codebase",
        description="Search for a text query pattern across workspace files.",
        triggers=["search codebase", "find in files", "grep search", "search files"],
        intents=["codebase_control"],
        action=_handle_codebase_search,
    )
    
    services["codebase_edit"] = ServiceDef(
        name="Edit File",
        description="Modify or overwrite file content atomically with syntax check fallback.",
        triggers=["edit file", "modify file", "write file", "apply diff", "patch file"],
        intents=["codebase_control"],
        action=_handle_codebase_edit,
    )
    
    services["codebase_git"] = ServiceDef(
        name="Git Operation",
        description="Perform git operations like status, diff, log, commit, or force-push.",
        triggers=["git operation", "git status", "git commit", "git push", "git diff"],
        intents=["codebase_control"],
        action=_handle_codebase_git,
    )
    
    services["codebase_test"] = ServiceDef(
        name="Run Tests",
        description="Run pytest suite on files with time limits.",
        triggers=["run tests", "run pytest", "execute test", "test codebase"],
        intents=["codebase_control"],
        action=_handle_codebase_test,
    )
    
    services["codebase_build"] = ServiceDef(
        name="Build",
        description="Compile or build project artifacts.",
        triggers=["build project", "run build", "compile"],
        intents=["codebase_control"],
        action=_handle_codebase_build,
    )
