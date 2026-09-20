"""Static guardrails for the active Stage 4 module boundaries."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server" / "app" / "server.py"
ROUTES = ROOT / "server" / "app" / "routes"
DOMAIN_ROOTS = (
    "server/app",
    "server/agents",
    "thursday",
    "studio/kenn/kenn",
    "studio/audio_analysis/audio_analysis",
    "studio/audiogen/audiogen",
)


def test_pytest_path_does_not_expose_thursday_modules_as_top_level() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pythonpath = config["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert "thursday" not in pythonpath


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_composition_root_remains_reduced() -> None:
    assert line_count(SERVER) <= 400


def test_route_modules_remain_near_the_500_line_budget() -> None:
    oversized = {
        path.name: line_count(path)
        for path in ROUTES.glob("*.py")
        if line_count(path) > 550
    }
    assert oversized == {}


def test_route_modules_do_not_import_the_composition_root() -> None:
    offenders = []
    for path in ROUTES.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "import app.server" in source or "from app.server" in source:
            offenders.append(path.name)
    assert offenders == []


def test_delivery_and_policy_implementations_live_outside_composition_root() -> None:
    server = SERVER.read_text(encoding="utf-8")
    assert "def serve_static" not in server
    assert "def serve_invoice" not in server
    assert "def send_audio_file_range" not in server
    assert "def route_access" not in server
    assert "def safe_error_payload" not in server


def _module_graph() -> tuple[dict[str, set[str]], dict[str, str]]:
    modules: dict[str, Path] = {}
    module_domain: dict[str, str] = {}
    for domain in DOMAIN_ROOTS:
        for path in (ROOT / domain).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            parts = list(path.relative_to(ROOT).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            name = ".".join(parts)
            modules[name] = path
            module_domain[name] = domain

    names = set(modules)
    graph = {name: set() for name in names}
    for current, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = current.split(".")[:-1]
                    keep = max(0, len(parent) - node.level + 1)
                    prefix = ".".join(parent[:keep])
                    candidates = [
                        ".".join(part for part in (prefix, node.module or "") if part)
                    ]
                elif node.module:
                    candidates = [node.module]
            for candidate in candidates:
                probe = candidate
                while probe:
                    if probe in names:
                        if probe != current:
                            graph[current].add(probe)
                        break
                    probe = probe.rpartition(".")[0]
    return graph, module_domain


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        components.append(component)

    for node in graph:
        if node not in indices:
            visit(node)
    return components


def test_no_import_cycle_crosses_domain_package_boundaries() -> None:
    graph, module_domain = _module_graph()
    cross_domain_cycles = []
    for component in _strongly_connected_components(graph):
        domains = {module_domain[module] for module in component}
        if len(component) > 1 and len(domains) > 1:
            cross_domain_cycles.append(sorted(component))
    assert cross_domain_cycles == []


_FORBIDDEN_IMPORT_RE = re.compile(r"^\s*(from|import)\s+(app|kenn)(\.|\s|$)", re.MULTILINE)


_ARCH_BOUNDARY_ALLOWLIST = {
    # mix_intent.py is an explicit cross-layer bridge (M8.5) that calls the KENN LM
    # to parse natural language instructions — by design it links audio_analysis + KENN.
    "studio/audio_analysis/audio_analysis/integration/mix_intent.py",
    # kenn_handoff.py is Stage 9's explicit cross-layer bridge: it reuses KENN's
    # real answer pipeline (chat_answer.answer_payload) to ground AutoMix parameter
    # and Mix Review flag explanations in cited notes, by design.
    "studio/audio_analysis/audio_analysis/integration/kenn_handoff.py",
    # kenn_advisor.py is the deterministic shadow-mode advisor producer: it queries
    # KENN's retrieval directly so proposals abstain unless grounded in the exact
    # approved AutoMix note, by design (see docs/KENN_AUTOMIX_ADVISOR_CONTRACT_V1.md).
    "studio/audio_analysis/audio_analysis/integration/kenn_advisor.py",
}


def test_audio_analysis_does_not_import_application_or_kenn_implementations() -> None:
    offenders = []
    for path in (ROOT / "studio" / "audio_analysis").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in _ARCH_BOUNDARY_ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        if _FORBIDDEN_IMPORT_RE.search(source):
            offenders.append(rel)
    assert offenders == []
