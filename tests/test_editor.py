"""Tests for EditorialEngine."""

from md_audit.editor import EditorialEngine
from md_audit.scanner import ScannedDocument, mask_markdown_prose, count_prose_words
from pathlib import Path


def make_doc(content: str, path: str = "test.md") -> ScannedDocument:
    raw_lines = content.splitlines()
    prose_lines = mask_markdown_prose(content)
    words = count_prose_words(prose_lines)
    return ScannedDocument(
        path=path,
        absolute_path=Path(path),
        raw_content=content,
        raw_lines=raw_lines,
        prose_lines=prose_lines,
        word_count=words,
        char_count=len(content),
    )


def test_editor_improves_wordiness_and_cliches():
    text = (
        "# Overview\n\n"
        "In order to run tests, use `pytest`.\n"
        "This project stands as a testament to clean architecture.\n"
        "We utilize caching due to the fact that speed matters.\n"
    )
    doc = make_doc(text)
    engine = EditorialEngine()
    res = engine.improve_document(doc)

    assert res.is_safe
    assert res.changes_count > 0
    assert "In order to" not in res.revised_content
    assert "stands as a testament to" not in res.revised_content
    assert "utilize" not in res.revised_content
    assert "due to the fact that" not in res.revised_content
    # Code block inline is untouched
    assert "`pytest`" in res.revised_content


def test_editor_preserves_code_fences():
    text = (
        "# Guide\n\n"
        "Teams utilize the following script in order to deploy:\n\n"
        "```python\n"
        "def utilize():\n"
        "    return 'in order to'\n"
        "```\n"
    )
    doc = make_doc(text)
    engine = EditorialEngine()
    res = engine.improve_document(doc)

    assert res.is_safe
    # Prose changed
    assert "Teams use the following script to deploy:" in res.revised_content
    # Code fence completely preserved
    assert "def utilize():" in res.revised_content
    assert "return 'in order to'" in res.revised_content
