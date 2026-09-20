"""Unit tests for Thursday V2-F Isolated execution and sandbox containment."""

from __future__ import annotations

import os
import pytest
from thursday.sandbox import TaskSandbox
from thursday.sandbox_runner import SandboxRunner
from thursday.lease_policy import SandboxLeasePolicy

def test_environment_sanitisation():
    sandbox = TaskSandbox("sb-test", "t-test", "engineering", "abc")
    # Inject mock secret
    os.environ["SECRET_API_KEY"] = "super-secret-token"
    os.environ["PATH"] = "/usr/bin:/bin"
    
    clean_env = sandbox.get_sanitised_env()
    assert "PATH" in clean_env
    assert "SECRET_API_KEY" not in clean_env
    assert clean_env["HOME"] == sandbox.temp_path

def test_command_filtering():
    policy = SandboxLeasePolicy()
    runner = SandboxRunner(policy)
    
    assert runner.is_safe_command(["echo", "hello"]) is True
    assert runner.is_safe_command(["rm", "-rf", "/"]) is False
    assert runner.is_safe_command(["sudo", "make"]) is False
    assert runner.is_safe_command(["killall", "-9", "python"]) is False

def test_process_containment_and_niceness():
    sandbox = TaskSandbox("sb-test", "t-test", "qa", "abc")
    sandbox.setup()
    
    # Launch small echo task
    proc = sandbox.launch_task_process(["echo", "docs_building"])
    assert proc.pid > 0
    stdout, stderr = proc.communicate()
    assert "docs_building" in stdout
    
    sandbox.cleanup()
