#!/usr/bin/env python3
"""Reject staged files that do not belong in the repository or expose local data."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath

ALLOWED_ROOTS = {
    ".githooks",
    "autostart",
    "docs",
    "examples",
    "scripts",
    "src",
    "systemd",
    "tests",
    "udev",
}
ALLOWED_ROOT_FILES = {
    ".gitleaks.toml",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "check_manifest.py",
    "pyproject.toml",
    "ulanzi_d200_upstream.py",
}
FORBIDDEN_NAMES = {
    ".bash_profile",
    ".bashrc",
    ".gitconfig",
    ".gitmodules",
    ".mcp.json",
    ".profile",
    ".ripgreprc",
    ".zprofile",
    ".zshrc",
    "service_env.txt",
    "session_env.txt",
}
FORBIDDEN_PARTS = {
    ".copilot-temp",
    ".idea",
    ".playwright-mcp",
    ".pytest_cache",
    ".vscode",
    "__pycache__",
}
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")),
    (
        "assigned credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|passwd|secret[_-]?key|"
            r"access[_-]?token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"
        ),
    ),
)
ENVIRONMENT_MARKERS = re.compile(
    r"^(?:DBUS_SESSION_BUS_ADDRESS|DISPLAY|HOME|INVOCATION_ID|JOURNAL_STREAM|PATH|PWD|"
    r"SESSION_MANAGER|SSH_AUTH_SOCK|USER|XAUTHORITY|XDG_RUNTIME_DIR)="
)
PERSONAL_HOME = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)/")
HOME_PLACEHOLDERS = {"me", "test", "user", "username"}


def validate_path(path_text: str) -> list[str]:
    path = PurePosixPath(path_text)
    findings: list[str] = []
    if path.name in FORBIDDEN_NAMES or FORBIDDEN_PARTS.intersection(path.parts):
        findings.append("local, generated, or user-specific path")
    if len(path.parts) == 1:
        if path_text not in ALLOWED_ROOT_FILES:
            findings.append("top-level file is not explicitly approved")
    elif path.parts[0] not in ALLOWED_ROOTS:
        findings.append("top-level directory is not explicitly approved")
    return findings


def validate_content(content: bytes) -> list[str]:
    if b"\0" in content:
        return []
    text = content.decode("utf-8", errors="replace")
    findings = [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]
    if sum(bool(ENVIRONMENT_MARKERS.match(line)) for line in text.splitlines()) >= 4:
        findings.append("shell/session environment dump")
    personal_users = {
        match.group(1) for match in PERSONAL_HOME.finditer(text)
        if match.group(1).lower() not in HOME_PLACEHOLDERS
    }
    if personal_users:
        findings.append("personal absolute home path")
    return findings


def staged_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def staged_content(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f":{path}"], check=True, capture_output=True
    ).stdout


def check_entries(entries: list[tuple[str, bytes]]) -> list[str]:
    failures: list[str] = []
    for path, content in entries:
        reasons = validate_path(path) + validate_content(content)
        if reasons:
            failures.append(f"{path}: {', '.join(dict.fromkeys(reasons))}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="read files from Git's index")
    args = parser.parse_args()
    if not args.staged:
        parser.error("--staged is required")

    failures = check_entries([(path, staged_content(path)) for path in staged_paths()])
    if failures:
        print("Repository hygiene check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
