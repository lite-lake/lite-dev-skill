#!/usr/bin/env python3
"""Check that every carrier of the version agrees.

The version lives in `flowlib/__init__.py`; the changelogs, the profile
template, and the bundled extensions each restate it. A release that updates
one and not the others ships a contract that contradicts itself, so this is a
gate rather than a convention.

`--sync` copies the root changelogs into `skills/lite-dev/`, where an installed
copy can read them offline; the copies are generated and never edited by hand.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "lite-dev"
PAIRS = ("CHANGELOG.md", "CHANGELOG.zh.md")

sys.path.insert(0, str(SKILL / "scripts"))
from flowlib.profile import ProfileError, satisfies  # noqa: E402
from flowlib.scaffold import compat_range  # noqa: E402

_VERSION_LINE = re.compile(r'(?m)^__version__ = "([^"]+)"$')
_RELEASE = re.compile(r"(?m)^##\s+(\d+\.\d+\.\d+)\b")
_ANY_H2 = re.compile(r"(?m)^##\s+")


def version_of(root: Path) -> str:
    try:
        text = (root / "skills/lite-dev/scripts/flowlib/__init__.py").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise SystemExit(f"error: cannot read the version file: {exc}")
    match = _VERSION_LINE.search(text)
    if not match:
        raise SystemExit("error: flowlib/__init__.py has no __version__ = \"...\" line")
    return match.group(1)


def releases(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}")
    return _RELEASE.findall(text)


def h2_count(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}")
    return len(_ANY_H2.findall(text))


def tag_at_head(root: Path) -> str:
    process = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        return ""
    tags = [line.strip() for line in process.stdout.splitlines() if line.strip()]
    versioned = [tag for tag in tags if tag.startswith("v")]
    return versioned[0] if versioned else ""


def check(root: Path, *, tag: str = "") -> list[str]:
    """Return errors; an empty list means every carrier agrees."""
    errors: list[str] = []
    version = version_of(root)
    try:
        window = compat_range(version)
    except ProfileError as exc:
        return [str(exc)]

    english = root / "CHANGELOG.md"
    chinese = root / "CHANGELOG.zh.md"
    en = releases(english)
    zh = releases(chinese)
    if not en or en[0] != version:
        errors.append(
            f"CHANGELOG.md starts at {en[0] if en else '(no release)'}, "
            f"but __version__ is {version}"
        )
    if not zh or zh[0] != version:
        errors.append(
            f"CHANGELOG.zh.md starts at {zh[0] if zh else '(no release)'}, "
            f"but __version__ is {version}"
        )
    if en != zh:
        errors.append(
            "CHANGELOG.md and CHANGELOG.zh.md list different versions; "
            "add the missing section to both, in the same order"
        )

    for name in PAIRS:
        root_file = root / name
        bundled = root / "skills" / "lite-dev" / name
        try:
            same = bundled.read_bytes() == root_file.read_bytes()
        except OSError as exc:
            errors.append(f"{bundled.relative_to(root)}: {exc}; run --sync")
            continue
        if not same:
            errors.append(
                f"{bundled.relative_to(root)} is stale; run this script with --sync"
            )

    template_path = root / "skills/lite-dev/profile.template.toml"
    try:
        template = tomllib.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"{template_path.relative_to(root)}: {exc}")
        template = {}
    flow = template.get("flow") or {}
    if flow.get("requires") != window:
        errors.append(
            f"profile.template.toml requires {flow.get('requires')!r}, "
            f"but this version derives {window!r}"
        )
    if flow.get("reviewed") != version:
        errors.append(
            f"profile.template.toml reviewed {flow.get('reviewed')!r}, "
            f"but this version is {version!r}"
        )

    for extension in sorted((root / "skills/lite-dev/extensions").glob("*/extension.toml")):
        try:
            raw = tomllib.loads(extension.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{extension.relative_to(root)}: {exc}")
            continue
        requires = raw.get("requires", "")
        try:
            ok = bool(requires) and satisfies(version, requires)
        except ProfileError as exc:
            errors.append(f"{extension.relative_to(root)}: {exc}")
            continue
        if not ok:
            errors.append(
                f"{extension.relative_to(root)} requires {requires!r}, "
                f"which excludes {version}"
            )

    try:
        en_h2 = h2_count(root / "README.md")
        zh_h2 = h2_count(root / "README.zh.md")
    except SystemExit as exc:
        errors.append(str(exc))
        en_h2 = zh_h2 = -1
    if en_h2 >= 0 and zh_h2 >= 0 and en_h2 != zh_h2:
        errors.append(
            f"README.md has {en_h2} H2 sections and README.zh.md has {zh_h2}; "
            "keep the two structures paired"
        )

    current_tag = tag or tag_at_head(root)
    if current_tag:
        expected = f"v{version}"
        if current_tag not in (expected, version):
            errors.append(
                f"tag {current_tag} points at HEAD, but __version__ is {version}; "
                f"expected {expected}"
            )

    return errors


def sync(root: Path) -> None:
    for name in PAIRS:
        shutil.copyfile(root / name, root / "skills" / "lite-dev" / name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="check the version carriers agree")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    parser.add_argument("--tag", default="", help="release tag to compare (default: tag at HEAD)")
    parser.add_argument(
        "--sync", action="store_true", help="copy the root changelogs into the skill first"
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if args.sync:
        sync(root)
    errors = check(root, tag=args.tag)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(
            f"FAIL: {len(errors)} version carrier(s) disagree",
            file=sys.stderr,
        )
        return 1
    print(f"ok: lite-dev {version_of(root)} — version, changelogs, template and extensions agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
