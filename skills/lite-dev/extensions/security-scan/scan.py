#!/usr/bin/env python3
"""Fail when a git-tracked file looks like a committed credential.

Generic on purpose: the rules are shapes (private keys, access keys, URLs with
inline credentials, JWT, secret assignments), and the allowlist is project data.
Run it from the project root; it reads `git ls-files`, so nothing untracked and
nothing inside `.git` is scanned.

    python3 scan.py [--allow docs/flow/security-allow.txt]

Exit codes: 0 clean, 1 findings, 2 not a repository.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 512 * 1024
BINARY_PROBE = 8192
ALLOW_MARKER = "lite-dev: allow"
DEFAULT_ALLOW = "docs/flow/security-allow.txt"
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", ".netrc", ".pgpass"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}

RULES: list[tuple[str, re.Pattern]] = [
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("cloud-access-key", re.compile(r"\b(?:AKIA|ASIA|LTAI)[0-9A-Za-z]{12,20}\b")),
    ("credentialed-url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@")),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(?:secret|token|password|passwd|api[_-]?key|access[_-]?key)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]


def tracked_files(root: Path) -> list[str]:
    process = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise SystemExit(f"git ls-files failed: {process.stderr.strip()}")
    return [entry for entry in process.stdout.split("\0") if entry]


def read_allowlist(root: Path, relative: str) -> list[str]:
    path = root / relative
    if not path.is_file():
        return []
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def allowed(entry: str, allowlist: list[str]) -> bool:
    return any(entry == item or entry.startswith(item) for item in allowlist)


def findings_for(path: Path, entry: str) -> list[str]:
    findings: list[str] = []
    name = Path(entry).name
    if name in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
        findings.append(f"{entry}: sensitive file is tracked")
    try:
        if path.stat().st_size > MAX_BYTES:
            return findings
        data = path.read_bytes()
    except OSError:
        return findings
    if b"\0" in data[:BINARY_PROBE]:
        return findings
    text = data.decode("utf-8", "replace")
    for number, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for label, pattern in RULES:
            if pattern.search(line):
                findings.append(f"{entry}:{number}: {label}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="scan git-tracked files for credentials")
    parser.add_argument("--allow", default=DEFAULT_ALLOW, help="allowlist file (path prefixes)")
    args = parser.parse_args(argv)

    root = Path.cwd()
    process = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0 or process.stdout.strip() != "true":
        print("error: not a git repository; the scan reads tracked files only")
        return 2

    allowlist = read_allowlist(root, args.allow)
    findings: list[str] = []
    scanned = 0
    for entry in tracked_files(root):
        if allowed(entry, allowlist):
            continue
        path = root / entry
        if not path.is_file():
            continue
        scanned += 1
        findings.extend(findings_for(path, entry))

    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {scanned} tracked file(s)")
        for finding in findings:
            print(f"  {finding}")
        print("  fix: remove the value, rotate it, and record a false positive in " + args.allow)
        return 1
    print(f"PASS: {scanned} tracked file(s); no credentials found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
