"""Canonical product paths for KENN's reorganised workspace.

Keep repository layout knowledge here instead of deriving different parent
counts throughout the backend.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parent
BACKEND_ROOT = SOURCE_ROOT.parent
APPS_ROOT = BACKEND_ROOT.parent
PRODUCT_ROOT = APPS_ROOT.parent

FRONTEND_ROOT = APPS_ROOT / "frontend"
LEGACY_WEB_ROOT = APPS_ROOT / "legacy-web"
DESKTOP_ROOT = APPS_ROOT / "desktop"
PACKAGES_ROOT = PRODUCT_ROOT / "packages"
PLUGINS_ROOT = PRODUCT_ROOT / "plugins"
INTEGRATIONS_ROOT = PRODUCT_ROOT / "integrations"
TOOLING_ROOT = PRODUCT_ROOT / "tooling"
DOCS_ROOT = PRODUCT_ROOT / "docs"
RUNTIME_ROOT = Path(os.environ.get("KENN_RUNTIME_ROOT", str(PRODUCT_ROOT / ".runtime"))).expanduser().resolve()
