"""Markdown file discovery and prose extraction scanner."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_EXCLUSIONS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "revised",
    "reports",
    "scratch",
}


@dataclass
class ScannedDocument:
    """Represents a scanned Markdown document with raw content and masked prose."""
    path: str  # Path relative to scanning root
    absolute_path: Path
    raw_content: str
    raw_lines: list[str]
    prose_lines: list[str]
    word_count: int
    char_count: int

    @property
    def prose_content(self) -> str:
        return "\n".join(self.prose_lines)


def mask_markdown_prose(raw_content: str) -> list[str]:
    """
    Mask non-prose elements (code blocks, frontmatter, inline code, HTML comments)
    while strictly preserving line numbers and character lengths where possible.
    """
    lines = raw_content.splitlines()
    prose_lines: list[str] = []

    in_frontmatter = False
    in_code_fence = False
    fence_char = ""
    in_html_comment = False

    # Check for frontmatter at the very top of file
    starts_with_frontmatter = len(lines) > 0 and lines[0].strip() == "---"

    for idx, line in enumerate(lines):
        # Handle YAML frontmatter at start
        if idx == 0 and starts_with_frontmatter:
            in_frontmatter = True
            prose_lines.append("")
            continue

        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            prose_lines.append("")
            continue

        # Handle multi-line HTML comments
        stripped = line.strip()
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            prose_lines.append("")
            continue
        elif stripped.startswith("<!--") and "-->" not in line:
            in_html_comment = True
            prose_lines.append("")
            continue
        elif stripped.startswith("<!--") and stripped.endswith("-->"):
            prose_lines.append("")
            continue

        # Handle fenced code blocks (``` or ~~~)
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            fence = fence_match.group(1)
            if not in_code_fence:
                in_code_fence = True
                fence_char = fence[0]
                prose_lines.append("")
                continue
            elif fence[0] == fence_char and len(fence) >= 3:
                in_code_fence = False
                fence_char = ""
                prose_lines.append("")
                continue

        if in_code_fence:
            prose_lines.append("")
            continue

        # For normal prose line, mask inline code: `code` -> spaces of same length
        prose_line = re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group(0)), line)
        # Mask image links: ![alt](url) -> ![alt]()
        prose_line = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", prose_line)
        # Mask raw URLs in markdown links: [text](http://...) -> text
        prose_line = re.sub(r"\[([^\]]+)\]\((?:https?://|mailto:|file://)[^)]+\)", r"\1", prose_line)
        # Mask autolinks: <https://...> -> spaces
        prose_line = re.sub(r"<https?://[^>]+>", lambda m: " " * len(m.group(0)), prose_line)

        prose_lines.append(prose_line)

    return prose_lines


def count_prose_words(prose_lines: Sequence[str]) -> int:
    """Calculate approximate word count for prose sections."""
    text = " ".join(prose_lines)
    # Strip markdown headers, table separators, etc.
    cleaned = re.sub(r"[#*_~`|\-\+]+", " ", text)
    words = [w for w in re.split(r"\s+", cleaned) if w.strip()]
    return max(1, len(words))


def scan_directory(
    root_dir: str | Path,
    exclusions: Sequence[str] | None = None,
    custom_exclusions: Sequence[str] | None = None,
) -> list[ScannedDocument]:
    """
    Recursively discover all markdown files within root_dir, respecting exclusions.
    """
    root_path = Path(root_dir).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Directory not found: {root_path}")

    all_exclusions = set(exclusions or DEFAULT_EXCLUSIONS)
    if custom_exclusions:
        all_exclusions.update(custom_exclusions)

    documents: list[ScannedDocument] = []

    # If root_path is a single file
    if root_path.is_file():
        if root_path.suffix.lower() in {".md", ".markdown"}:
            raw = root_path.read_text(encoding="utf-8", errors="replace")
            raw_lines = raw.splitlines()
            prose_lines = mask_markdown_prose(raw)
            words = count_prose_words(prose_lines)
            documents.append(
                ScannedDocument(
                    path=root_path.name,
                    absolute_path=root_path,
                    raw_content=raw,
                    raw_lines=raw_lines,
                    prose_lines=prose_lines,
                    word_count=words,
                    char_count=len(raw),
                )
            )
        return documents

    for root, dirs, files in os.walk(root_path):
        # Modify dirs in-place to prevent descending into excluded directories
        dirs[:] = [
            d
            for d in dirs
            if d not in all_exclusions
            and not any(excl.startswith("*") and Path(d).match(excl) for excl in all_exclusions)
        ]

        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() not in {".md", ".markdown"}:
                continue

            rel_path = file_path.relative_to(root_path).as_posix()

            # Check if any relative path component matches exclusions
            path_parts = set(Path(rel_path).parts)
            if any(part in all_exclusions for part in path_parts):
                continue

            try:
                raw = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                # Log or handle unreadable files
                continue

            raw_lines = raw.splitlines()
            prose_lines = mask_markdown_prose(raw)
            words = count_prose_words(prose_lines)

            documents.append(
                ScannedDocument(
                    path=rel_path,
                    absolute_path=file_path,
                    raw_content=raw,
                    raw_lines=raw_lines,
                    prose_lines=prose_lines,
                    word_count=words,
                    char_count=len(raw),
                )
            )

    documents.sort(key=lambda doc: doc.path)
    return documents
