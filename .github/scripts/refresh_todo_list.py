#!/usr/bin/env python3
"""Apply TODO-list line/entry changes introduced between main and dev."""
from __future__ import annotations

import re
import sys
from pathlib import Path

README_PATH = Path("README.md")

UTILS = "luffy/deepscaler/utils.py"
PROTOCOL = "luffy/verl/verl/protocol.py"

# Baseline README line -> current dev line for TODOs that remain.
LINE_MAP = {
    UTILS: {
        50: 45,
        51: 46,
        52: 47,
        88: 107,
        89: 108,
        90: 109,
        91: 110,
        92: 111,
        93: 112,
        94: 113,
        95: 114,
    },
    PROTOCOL: {
        117: 114,
        118: 115,
        133: 136,
        135: 137,
        156: 169,
        252: 265,
        338: 351,
    },
}

# Baseline README lines whose TODOs were implemented and therefore removed.
REMOVE_LINES = {
    UTILS: {45, 46, 47, 48, 49},
    PROTOCOL: {114, 115, 116, 131, 132, 134},
}

# Exact current dev TODO line sets for the two changed files.
EXPECTED_LINES = {
    UTILS: {45, 46, 47, 107, 108, 109, 110, 111, 112, 113, 114},
    PROTOCOL: {114, 115, 136, 137, 169, 265, 351},
}

ITEM_RE = re.compile(
    r"^- \[ \] \*\*(?P<path>.+?):(?P<line>\d+)\*\*(?: - (?P<msg>.*))?$"
)


def todo_lines(path: str) -> list[int]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"missing source file: {path}")
    lines = []
    for idx, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if raw.strip().startswith("# TODO"):
            lines.append(idx)
    return lines


def main() -> int:
    if not README_PATH.exists():
        raise SystemExit("README.md not found")

    text = README_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    heading_idx = None
    for idx, line in enumerate(lines):
        if line.startswith("### ") and "Complete TODO List" in line:
            heading_idx = idx
            break
    if heading_idx is None:
        raise SystemExit("Complete TODO List heading not found")

    end_idx = None
    for idx in range(heading_idx + 1, len(lines)):
        if lines[idx].startswith("## "):
            end_idx = idx
            break
    if end_idx is None:
        raise SystemExit("End of Complete TODO List section not found")

    raw_items: list[dict] = []
    for idx in range(heading_idx + 1, end_idx):
        raw = lines[idx]
        if not raw.strip():
            continue
        m = ITEM_RE.match(raw)
        if not m:
            raise SystemExit(f"Unparsed README TODO line {idx + 1}: {raw!r}")
        raw_items.append(
            {
                "path": m.group("path"),
                "line": int(m.group("line")),
                "raw": raw,
            }
        )

    print(f"Parsed {len(raw_items)} existing TODO items")

    changed_paths = {UTILS, PROTOCOL}
    kept_items = [item for item in raw_items if item["path"] not in changed_paths]
    updated_items: list[dict] = []

    for item in raw_items:
        path = item["path"]
        old_line = item["line"]
        if path not in changed_paths:
            continue
        if old_line in REMOVE_LINES[path]:
            continue
        mapping = LINE_MAP[path]
        if old_line not in mapping:
            raise SystemExit(
                f"No line mapping for retained TODO {path}:{old_line}; refusing to guess"
            )
        new_line = mapping[old_line]
        old_marker = f"**{path}:{old_line}**"
        new_marker = f"**{path}:{new_line}**"
        if old_marker not in item["raw"]:
            raise SystemExit(f"Could not locate marker {old_marker} in {item['raw']!r}")
        new_raw = item["raw"].replace(old_marker, new_marker, 1)
        updated_items.append({"path": path, "line": new_line, "raw": new_raw})

    all_items = kept_items + updated_items
    all_items.sort(key=lambda item: (item["path"], item["line"]))

    # Validate the two reconciled files against the actual dev source.
    for path in sorted(changed_paths):
        source_todos = todo_lines(path)
        expected_source = EXPECTED_LINES[path]
        if set(source_todos) != expected_source:
            raise SystemExit(
                f"{path}: source TODO lines {source_todos} do not match "
                f"expected {sorted(expected_source)}"
            )
        listed_lines = {
            item["line"] for item in updated_items if item["path"] == path
        }
        if listed_lines != expected_source:
            raise SystemExit(
                f"{path}: updated README lines {sorted(listed_lines)} do not match "
                f"source TODO lines {sorted(expected_source)}"
            )

    keys = [(item["path"], item["line"]) for item in all_items]
    if keys != sorted(keys):
        raise SystemExit("Internal error: sorted item order was not stable")

    # Diagnostic: scan every Python file for TODO markers.
    py_files = sorted(p for p in Path(".").rglob("*.py") if ".git" not in p.parts)
    total_source_todos = 0
    per_file_counts: dict[str, int] = {}
    for py in py_files:
        count = len(todo_lines(py.as_posix()))
        if count:
            per_file_counts[py.as_posix()] = count
            total_source_todos += count
    print(f"Scanned {len(py_files)} Python files; found {total_source_todos} TODO markers")
    readme_counts: dict[str, int] = {}
    for item in raw_items:
        readme_counts[item["path"]] = readme_counts.get(item["path"], 0) + 1
    mismatches = []
    for path, count in sorted(per_file_counts.items()):
        if readme_counts.get(path, 0) != count:
            mismatches.append((path, count, readme_counts.get(path, 0)))
    print(f"Files with differing README/source TODO counts: {len(mismatches)}")
    for path, source_count, readme_count in mismatches[:60]:
        print(f"  {path}: source={source_count} readme={readme_count}")

    # Rebuild the section while preserving the heading and surrounding text.
    output_lines = lines[: heading_idx + 1]
    output_lines.append("")
    output_lines.extend(item["raw"] for item in all_items)
    output_lines.append("")
    output_lines.extend(lines[end_idx:])
    output_text = "\n".join(output_lines)
    if text.endswith("\n"):
        output_text += "\n"

    README_PATH.write_text(output_text, encoding="utf-8")

    # Remove temporary automation files so final tree only contains README change.
    for rel in (
        Path(".github/scripts/refresh_todo_list.py"),
        Path(".github/workflows/refresh-todo-list.yml"),
    ):
        try:
            rel.unlink()
        except FileNotFoundError:
            pass
    for d in (Path(".github/scripts"), Path(".github/workflows"), Path(".github")):
        try:
            d.rmdir()
        except OSError:
            pass

    print(f"Wrote {len(all_items)} TODO items; removed 11 completed items")
    print("Utils lines:", sorted(EXPECTED_LINES[UTILS]))
    print("Protocol lines:", sorted(EXPECTED_LINES[PROTOCOL]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
