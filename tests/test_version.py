#!/usr/bin/env python3
"""
Unit tests for project version metadata and consistency.

Ensures that:
1. Canonical version in src/gex/__init__.py conforms to Semantic Versioning (SemVer 2.0.0).
2. pyproject.toml package version strictly matches src/gex/__init__.__version__.
3. The CLI root argument parser exposes a functional --version flag reflecting the package version.
"""

import re
import unittest
from pathlib import Path

import src.gex
from src.gex.cli.parser import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

SEMVER_REGEX = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def extract_pyproject_version() -> str:
    """Parses project.version from pyproject.toml."""
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("version") and "=" in line:
            parts = line.split("=", 1)
            return parts[1].strip().strip("'\"")
    raise ValueError("version key not found in pyproject.toml")


class TestProjectVersion(unittest.TestCase):
    def test_version_defined(self):
        """Ensure src/gex.__version__ is defined as a non-empty string."""
        self.assertTrue(hasattr(src.gex, "__version__"))
        self.assertIsInstance(src.gex.__version__, str)
        self.assertTrue(bool(src.gex.__version__))

    def test_version_conforms_to_semver(self):
        """Ensure src/gex.__version__ adheres to SemVer (X.Y.Z)."""
        match = SEMVER_REGEX.match(src.gex.__version__)
        self.assertIsNotNone(
            match,
            f"Version '{src.gex.__version__}' does not adhere to Semantic Versioning 2.0.0",
        )

    def test_pyproject_version_matches_init_version(self):
        """Ensure pyproject.toml version strictly matches src/gex.__version__."""
        pyproject_ver = extract_pyproject_version()
        self.assertEqual(
            src.gex.__version__,
            pyproject_ver,
            f"Version mismatch: src/gex/__init__.py has '{src.gex.__version__}' "
            f"but pyproject.toml has '{pyproject_ver}'",
        )

    def test_cli_version_flag(self):
        """Ensure build_parser() includes a working --version action matching the package version."""
        parser = build_parser()
        with self.assertRaises(SystemExit) as cm:
            # Capturing the SystemExit(0) triggered by argparse version action
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                parser.parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertIn(src.gex.__version__, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
