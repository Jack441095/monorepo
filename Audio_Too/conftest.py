"""Root pytest configuration — nite_core, audio_analysis, kenn, and thursday
are installed editable (pip install -e) so they need no path injection.
Only non-package dirs that tests import directly still need sys.path help."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# Pre-import the server *package* before anything can shadow it with
# thursday/server.py (a module named "server" that isn't the package).
import importlib
_server_pkg = ROOT / "server"
if _server_pkg.is_dir() and (_server_pkg / "__init__.py").exists():
    if "server" not in sys.modules:
        sys.path.insert(0, str(ROOT))
        importlib.import_module("server")

PATHS_TO_INJECT = [
    ROOT / "studio" / "audiogen" / "audiogen",
    ROOT / "server" / "app",
    ROOT / "server" / "agents",
    ROOT / "scripts",
    ROOT / "studio",
    ROOT,
]

root_str = str(ROOT)
if root_str in sys.path:
    sys.path.remove(root_str)
sys.path.insert(0, root_str)

for p in reversed(PATHS_TO_INJECT):
    p_str = str(p)
    if p_str != root_str and p_str not in sys.path and p.exists():
        sys.path.insert(1, p_str)
