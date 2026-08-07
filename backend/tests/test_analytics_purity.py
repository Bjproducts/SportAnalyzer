"""Architectural guard: pure analytics must never acquire infrastructure imports."""

from __future__ import annotations

import ast
from pathlib import Path

ANALYTICS_ROOT = Path(__file__).parents[1] / "app" / "analytics"
FORBIDDEN_PREFIXES = (
    "sqlalchemy",
    "httpx",
    "app.api",
    "app.database",
    "app.ingestion",
    "app.models",
    "app.repositories",
    "app.services",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_analytics_package_has_no_database_http_or_provider_dependencies():
    violations: list[str] = []

    for path in sorted(ANALYTICS_ROOT.glob("*.py")):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path.name}: {imported}")

    assert violations == [], "Pure analytics import violations: " + ", ".join(violations)
