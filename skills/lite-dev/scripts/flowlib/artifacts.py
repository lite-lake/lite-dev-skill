"""Parsing and derivation for item.md and design.md.

Artifact headings are a parsing contract: they are English and stable even when
the prose inside them is written in any language.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import fsio
from .errors import FlowError
from .profile import Profile

FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.S)
HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)
AC_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s*(AC\d{2,3})\b[ \t]*(.*)$", re.M)
MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CLARIFIED = {"clarified", "confirmed", "ready", "已澄清", "已确认", "无歧义"}
DROPPED = {"dropped", "cancelled", "canceled", "已放弃"}
PLACEHOLDER_RE = re.compile(r"<[A-Za-z][^<>\n]*>")

ITEM_FIELDS = ("id", "title", "type", "priority", "size", "mode", "owner", "created")

# Archived items keep their month bucket under this name. It is not a month, so
# the layout check and the item listing both have to know about it explicitly.
ARCHIVE_DIR = "_archive"

# The directory slug follows the title's script: a Chinese title keeps its
# characters, anything else is word-joined with '-'. Width is counted in
# characters, so 30 Chinese characters read like 60 columns.
SLUG_WIDE_MAX = 30
SLUG_COMFORT = 20
SLUG_ASCII_MAX = 32


def month_of(created: str) -> str:
    """The bucket an item lives in: '2026-11-26' -> '2026-11'."""
    return created.strip()[:7]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FM_RE.match(text.lstrip("\ufeff"))
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, match.group(2)


def set_frontmatter_values(path: Path, values: dict[str, str]) -> None:
    """Set several frontmatter keys in one read and one atomic write."""
    text = read_text(path)
    match = FM_RE.match(text.lstrip("\ufeff"))
    if not match:
        raise ValueError(f"{path} has no frontmatter")
    lines = match.group(1).splitlines()
    for key, value in values.items():
        pattern = re.compile(rf"^{re.escape(key)}\s*:")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = f"{key}: {value}"
                break
        else:
            lines.append(f"{key}: {value}")
    fsio.atomic_write_text(
        path,
        "---\n" + "\n".join(lines) + "\n---\n" + match.group(2),
    )


def set_frontmatter_value(path: Path, key: str, value: str) -> None:
    set_frontmatter_values(path, {key: value})


def sections(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    matches = list(HEADING_RE.finditer(body))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result.setdefault(match.group(1).strip(), body[match.end() : end].strip())
    return result


def section(body: str, *names: str) -> str | None:
    found = sections(body)
    for name in names:
        if name in found:
            return found[name]
    return None


def parse_ac(body: str) -> list[dict]:
    text = section(body, "AC") or ""
    return [
        {"id": match.group(2), "done": match.group(1).lower() == "x", "text": match.group(3).strip()}
        for match in AC_RE.finditer(text)
    ]


def parse_table(body: str, *headings: str) -> list[dict[str, str]]:
    text = section(body, *headings)
    if not text:
        return []
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if cells and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def row_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        for key, value in row.items():
            if key.strip().lower() == name.strip().lower():
                return value
    return ""


def relative_links(path: Path, text: str) -> list[str]:
    links: list[str] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0]
        if target and "://" not in target:
            links.append(target)
    return links


@dataclass
class Item:
    path: Path
    directory: Path
    meta: dict[str, str]
    body: str
    ac: list[dict]
    clarify: str
    design_path: Path | None
    design_meta: dict[str, str]
    design_body: str
    progress: list[dict[str, str]]

    @property
    def id(self) -> str:
        return self.meta.get("id", "")

    @property
    def size(self) -> str:
        return self.meta.get("size", "")

    @property
    def mode(self) -> str:
        return self.meta.get("mode", "")

    @property
    def ac_total(self) -> int:
        return len(self.ac)

    @property
    def ac_done(self) -> int:
        return sum(1 for entry in self.ac if entry["done"])

    @property
    def clarify_state(self) -> str:
        return self.clarify.strip().lower()

    @property
    def design_status(self) -> str:
        return (self.design_meta.get("status") or "").strip().lower()

    @property
    def status(self) -> str:
        closed = (self.meta.get("closed") or "").strip().lower()
        if closed in DROPPED:
            return "dropped"
        if closed:
            return "done"
        if self.design_path is not None:
            return "ready" if self.design_status == "ready" else "designing"
        if self.clarify_state in CLARIFIED:
            return "clarified"
        return "need-clarify"

    @property
    def batches(self) -> list[dict[str, str]]:
        return parse_table(self.design_body, "Batches", "实施批次")


def load_item(directory: Path) -> Item:
    path = directory / "item.md"
    meta, body = parse_frontmatter(read_text(path))
    clarify_text = section(body, "Clarify", "澄清") or ""
    match = re.search(r"^\s*[-*]\s*(?:Status|状态)\s*[:：]\s*(.+)$", clarify_text, re.M | re.I)
    design_path = directory / "design.md"
    design_meta: dict[str, str] = {}
    design_body = ""
    if design_path.is_file():
        design_meta, design_body = parse_frontmatter(read_text(design_path))
    return Item(
        path=path,
        directory=directory,
        meta=meta,
        body=body,
        ac=parse_ac(body),
        clarify=match.group(1).strip() if match else "",
        design_path=design_path if design_path.is_file() else None,
        design_meta=design_meta,
        design_body=design_body,
        progress=parse_table(body, "Implementation", "实施进度"),
    )


def _items_under(base: Path) -> list[Item]:
    if not base.is_dir():
        return []
    items = []
    for bucket in sorted(base.iterdir()):
        if not bucket.is_dir() or bucket.name == ARCHIVE_DIR:
            continue
        for directory in sorted(bucket.iterdir()):
            if directory.is_dir() and (directory / "item.md").is_file():
                items.append(load_item(directory))
    return items


def all_items(profile: Profile) -> list[Item]:
    """Open and finished items at <work_dir>/<YYYY-MM>/<id>-<slug>/item.md.

    Buckets are read whatever their name, so a misplaced item is still found and
    reported by `check` instead of disappearing from the listing. Archived items
    are not part of the working set; `find_item` still resolves them by id.
    """
    return _items_under(profile.work_path)


def archived_items(profile: Profile) -> list[Item]:
    return _items_under(profile.work_path / ARCHIVE_DIR)


def find_item(profile: Profile, item_id: str) -> Item:
    """Resolve an id exactly, or by a unique prefix. Never guess between matches."""
    query = (item_id or "").strip()
    if not query:
        raise FlowError("work item id is empty")
    items = all_items(profile) + archived_items(profile)
    exact = [item for item in items if item.id == query or item.directory.name == query]
    matches = exact or [
        item
        for item in items
        if item.id.startswith(query) or item.directory.name.startswith(query)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FlowError(f"work item not found: {query}")
    lines = [f"ambiguous work item {query!r}: {len(matches)} matches"]
    for item in matches:
        title = item.meta.get("title", "")
        lines.append(f"  {item.id}  {title}  ({item.status})  {_archive_label(item)}")
    lines.append("use the full id (flow.py status lists them)")
    raise FlowError("\n".join(lines))


def _archive_label(item: Item) -> str:
    return "archived" if ARCHIVE_DIR in item.directory.parts else "active"


def ac_ids(item: Item) -> list[str]:
    return [entry["id"] for entry in item.ac]
