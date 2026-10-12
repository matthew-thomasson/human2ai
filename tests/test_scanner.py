"""Tests for scanner and markdown masking."""

import tempfile
from pathlib import Path
from md_audit.scanner import mask_markdown_prose, scan_directory


def test_mask_markdown_prose():
    md_text = """---
title: Test Page
date: 2026-01-01
---

# Title

Here is `inline_code_delve` inside prose.

```python
def delve_into_code():
    return "testament"
```

<!-- HTML comment with delve into -->
Normal prose line.
"""
    lines = mask_markdown_prose(md_text)
    # Total lines must match exactly
    assert len(lines) == len(md_text.splitlines())

    # Frontmatter lines should be blank
    assert lines[0] == ""
    assert lines[1] == ""
    assert lines[2] == ""
    assert lines[3] == ""

    # Line 7 (0-indexed line 6) has inline code replaced with spaces of same length
    inline_line = lines[7]
    assert "`inline_code_delve`" not in inline_line
    assert "Here is" in inline_line

    # Code fence content should be masked
    assert "def delve_into_code():" not in "\n".join(lines)

    # HTML comments should be masked
    assert "HTML comment with delve into" not in "\n".join(lines)

    # Normal prose remains
    assert "Normal prose line." in lines[-1]


def test_scan_directory_exclusions(tmp_path: Path):
    # Setup test directory tree
    (tmp_path / "valid.md").write_text("# Valid\nSome prose.", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "doc.md").write_text("# Sub\nMore prose.", encoding="utf-8")

    # Excluded directories
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.md").write_text("# Git\nShould not be scanned.", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.md").write_text("# NPM\nShould not be scanned.", encoding="utf-8")

    docs = scan_directory(tmp_path)
    paths = [d.path for d in docs]

    assert "valid.md" in paths
    assert "sub/doc.md" in paths
    assert not any(".git" in p for p in paths)
    assert not any("node_modules" in p for p in paths)
