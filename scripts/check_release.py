#!/usr/bin/env python3
"""Verify that every public release-version declaration matches a Git tag."""
from __future__ import annotations

import argparse
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parent.parent


def match(pattern: str, path: pathlib.Path, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.search(pattern, text, re.MULTILINE)
    if not found:
        raise SystemExit(f"release check: cannot find {label} in {path.relative_to(ROOT)}")
    return found.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, for example v0.5.0")
    args = parser.parse_args()

    package_version = match(
        r'^PACKAGE_VERSION = "([^"]+)"$',
        ROOT / "scripts" / "install.py",
        "PACKAGE_VERSION",
    )
    expected_tag = f"v{package_version}"
    if args.tag != expected_tag:
        raise SystemExit(
            f"release check: tag {args.tag!r} does not match package version {package_version!r} "
            f"(expected {expected_tag!r})"
        )

    shell_version = match(
        r'^DEFAULT_VERSION="([^"]+)"$',
        ROOT / "site" / "install.sh",
        "shell bootstrap version",
    )
    powershell_version = match(
        r'^\$DefaultVersion = "([^"]+)"$',
        ROOT / "site" / "install.ps1",
        "PowerShell bootstrap version",
    )
    for label, value in (
        ("shell bootstrap", shell_version),
        ("PowerShell bootstrap", powershell_version),
    ):
        if value != expected_tag:
            raise SystemExit(f"release check: {label} pins {value!r}; expected {expected_tag!r}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(package_version)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE):
        raise SystemExit(f"release check: CHANGELOG.md has no dated {package_version} section")

    print(f"release contract valid: {expected_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
