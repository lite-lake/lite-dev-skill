#!/usr/bin/env python3
"""Check deployment manifests: complete, backfilled, and impossible to promote by alias.

A manifest is the atomic unit of a deployment: for each component, the commit it
was built from, the image it produced, and the rollback target. The checks are
generic — the manifest's content is the project's data.

    python3 deploy_check.py [--dir docs/releases/manifests] [--env <name>]

Exit codes: 0 all manifests valid (or none yet), 1 at least one invalid.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = "docs/releases/manifests"
ENV_VAR = "LITE_DEV_DEPLOY_DIR"

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
TAG_SHA_RE = re.compile(r"[0-9a-f]{7,40}")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,60}>")
ROLLBACK_NONE = {"", "none", "n/a", "—", "-"}

REQUIRED_FIELDS = ("environment", "deployed_at", "operator", "git", "images", "rollback")


def _strings(value, path: str = "") -> list[tuple[str, str]]:
    """Every string in the document with a dotted path, for the placeholder scan."""
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        found.append((path or ".", value))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(_strings(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_strings(item, f"{path}[{index}]"))
    return found


def _non_empty(value) -> bool:
    return bool(value) if not isinstance(value, str) else bool(value.strip())


def validate(manifest: dict, name: str, environment: str | None = None) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"missing '{field}'")
    if errors:
        return errors

    env = manifest.get("environment")
    if not isinstance(env, str) or not env.strip():
        errors.append("'environment' must be a non-empty string")
    elif environment and env.strip() != environment.strip():
        errors.append(f"'environment' is {env.strip()!r}, expected {environment.strip()!r}")

    deployed_at = manifest.get("deployed_at")
    if not isinstance(deployed_at, str) or not TIMESTAMP_RE.match(deployed_at.strip()):
        errors.append("'deployed_at' must be an RFC3339 timestamp, e.g. 2026-01-01T09:30:00Z")

    if not isinstance(manifest.get("operator"), str) or not manifest["operator"].strip():
        errors.append("'operator' must be a non-empty string")

    repos = manifest.get("git")
    if not isinstance(repos, dict) or not repos:
        errors.append("'git' must map each component to the commit it was built from")
    else:
        for component, sha in repos.items():
            if not isinstance(sha, str) or not SHA_RE.match(sha.strip()):
                errors.append(f"'git.{component}' must be a commit sha (7-40 hex), got {sha!r}")

    images = manifest.get("images")
    if not isinstance(images, list) or not images:
        errors.append("'images' must list at least one image")
    else:
        for index, image in enumerate(images):
            if not isinstance(image, dict):
                errors.append(f"'images[{index}]' must be an object")
                continue
            for key in ("repo", "tag", "digest"):
                if not isinstance(image.get(key), str) or not image[key].strip():
                    errors.append(f"'images[{index}].{key}' is required")
            tag = image.get("tag")
            if isinstance(tag, str) and tag.strip() and not TAG_SHA_RE.search(tag):
                errors.append(
                    f"'images[{index}].tag' ({tag}) is a floating tag; "
                    "use a tag that pins the commit, e.g. <environment>-<short-sha>"
                )
            digest = image.get("digest")
            if isinstance(digest, str) and digest.strip() and not DIGEST_RE.match(digest.strip()):
                errors.append(f"'images[{index}].digest' must be sha256:<64 hex>")

    rollback = manifest.get("rollback")
    if isinstance(rollback, str):
        text = rollback.strip().lower()
        if not text:
            errors.append("'rollback' must name a target; an empty value is not a plan")
        elif text in ROLLBACK_NONE - {""} and not manifest.get("first_deploy"):
            errors.append(
                "'rollback' says there is no previous target; set 'first_deploy: true' "
                "and describe the alternative path"
            )
    elif isinstance(rollback, dict):
        if not rollback:
            errors.append("'rollback' object is empty")
    else:
        errors.append("'rollback' must be a string or an object")

    for path, text in _strings(manifest):
        if PLACEHOLDER_RE.search(text):
            errors.append(f"{path} still contains a placeholder ({text.strip()[:40]})")

    return errors


def check_file(path: Path, environment: str | None) -> list[str]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read: {exc}"]
    except ValueError as exc:
        return [f"invalid JSON: {exc}"]
    if not isinstance(manifest, dict):
        return ["the manifest must be a JSON object"]
    return validate(manifest, path.name, environment)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate deployment manifests")
    parser.add_argument("--dir", help=f"manifest directory (default ${ENV_VAR} or {DEFAULT_DIR})")
    parser.add_argument("--env", help="require this environment in every manifest")
    args = parser.parse_args(argv)

    root = Path.cwd()
    directory = Path(args.dir or os.environ.get(ENV_VAR) or DEFAULT_DIR)
    if not directory.is_absolute():
        directory = root / directory
    if not directory.is_dir():
        print(f"PASS: no manifests in {directory.relative_to(root) if directory.is_relative_to(root) else directory}")
        print("  the deploy lane has not started here; nothing to check")
        return 0

    manifests = sorted(directory.glob("*.json"))
    if not manifests:
        print(f"PASS: no manifests in {directory.relative_to(root)}")
        return 0

    failed = 0
    for path in manifests:
        errors = check_file(path, args.env)
        name = path.relative_to(root) if path.is_relative_to(root) else path
        if errors:
            failed += 1
            print(f"FAIL {name}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {name}")

    if failed:
        print(f"\nFAIL: {failed} of {len(manifests)} manifest(s) are not recordable")
        print("  fix: backfill every field; a deployment with a placeholder did not happen")
        return 1
    print(f"\nPASS: {len(manifests)} manifest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
