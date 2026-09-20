"""Import-isolation tests: the platform core must be dependency-free and side-effect-free."""

import subprocess
import sys

FORBIDDEN_PREFIXES = (
    "torch",
    "onnx",
    "onnxruntime",
    "numpy",
    "scipy",
    "soundfile",
    "sounddevice",
    "httpx",
    "requests",
    "flask",
    "fastapi",
    "pydantic",
    "openai",
    "anthropic",
    "ollama",
    "sqlalchemy",
    "thursday",
    "kenn",
    "audio_too",
    "business",
)

SCRIPT = """
import sys
import nite_ai
import nite_ai.contracts
import nite_ai.capabilities
forbidden = {p for m in sys.modules for p in %r if m == p or m.startswith(p + ".")}
print("FORBIDDEN:", sorted(forbidden))
print("OK")
""" % (FORBIDDEN_PREFIXES,)


def test_import_has_no_heavy_or_product_dependencies() -> None:
    result = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "FORBIDDEN: []" in result.stdout


def test_import_creates_no_files_or_network() -> None:
    probe = (
        "import socket, nite_ai\n"
        "orig = socket.socket.connect\n"
        "socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network!'))\n"
        "import nite_ai.evaluation, nite_ai.telemetry\n"
        "print('NO-NETWORK-OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "NO-NETWORK-OK" in result.stdout


def test_version_metadata() -> None:
    import nite_ai

    assert nite_ai.__version__
    assert nite_ai.CONTRACT_SCHEMA_VERSION
