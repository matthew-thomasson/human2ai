"""Focused tests for POC enhancements: safe substitutions, model errors, LLM editor, reviewer, and portability."""

import pytest
from pathlib import Path
from md_audit.cli import get_default_config_path, get_default_rules_dir, load_config, main
from md_audit.editor import EditorialEngine, apply_safe_replacements, strip_leading_openers
from md_audit.llm import LLMEditor, LLMReviewer, ModelError, split_markdown_sections
from md_audit.scanner import ScannedDocument, count_prose_words, mask_markdown_prose


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


def test_unsafe_negative_parallelism_not_truncated():
    """Verify that sentences with negative parallelism are not blindly stripped."""
    text = "It's not encrypted with RSA, it's using AES-256."
    engine = EditorialEngine()
    doc = make_doc(text)
    res = engine.improve_document(doc)
    # The negative clause must NOT be deleted
    assert "It's not encrypted with RSA" in res.revised_content
    assert "AES-256" in res.revised_content


def test_strip_leading_openers_preserves_capitalization():
    """Verify that removing openers capitalizes the following word."""
    text = "Moreover, the system scales horizontally.\nIn conclusion, the results are positive."
    revised, changes = strip_leading_openers(text)
    assert changes == 2
    assert revised.startswith("The system scales horizontally.")
    assert "The results are positive." in revised
    assert "the system" not in revised


def test_safe_replacements_preserve_title_case():
    """Verify that replacements match the casing of the matched phrase."""
    text = "In order to initialize, run setup. We test due to the fact that quality matters."
    revised, changes = apply_safe_replacements(text)
    assert changes == 2
    # 'In order to' at start should become 'To', not 'to'
    assert revised.startswith("To initialize")
    assert "because quality matters" in revised


def test_markdown_preservation_elements():
    """Verify that headings, code blocks, tables, and links are preserved."""
    text = """# Section Heading

Here is an inline `my_variable` and a [link](https://example.com/api).

| Col1 | Col2 |
|---|---|
| val1 | val2 |

```python
def utilize():
    return "in order to"
```
"""
    doc = make_doc(text)
    engine = EditorialEngine()
    res = engine.improve_document(doc)
    assert res.is_safe
    assert "# Section Heading" in res.revised_content
    assert "`my_variable`" in res.revised_content
    assert "[link](https://example.com/api)" in res.revised_content
    assert "| Col1 | Col2 |" in res.revised_content
    assert "def utilize():" in res.revised_content


def test_model_error_raised_without_silent_mock():
    """Verify that ModelEvaluator raises ModelError when API key is missing in online mode."""
    from md_audit.analyzers.model_evaluator import ModelEvaluator
    evaluator = ModelEvaluator(api_key="", offline_mode=False)
    doc = make_doc("Sample prose.")
    with pytest.raises(ModelError, match="OPENROUTER_API_KEY is not set"):
        evaluator.evaluate(doc)


def test_split_markdown_sections():
    """Verify that long documents are chunked by headings without silent truncation."""
    doc_text = """# Header 1
First section content with some words.

## Header 2
Second section content with more explanations.

### Header 3
Third section content detailing technical steps.
"""
    # Max chars small enough to trigger split
    sections = split_markdown_sections(doc_text, max_chars=30)
    assert len(sections) >= 2
    reconstructed = "".join(sections)
    assert reconstructed.strip() == doc_text.strip()


def test_llm_editor_offline_modes():
    """Verify LLMEditor runs conservative and balanced offline modes."""
    editor = LLMEditor(offline_mode=True)
    text = "In today's fast-paced digital landscape, teams utilize automated pipelines in order to deploy."
    revised_bal = editor.rewrite(text, mode="balanced")
    assert "In today's fast-paced" not in revised_bal
    assert "Teams" in revised_bal

    revised_cons = editor.rewrite(text, mode="conservative")
    assert "in order to" not in revised_cons


def test_llm_reviewer_offline_decisions():
    """Verify LLMReviewer outputs valid decisions."""
    reviewer = LLMReviewer(offline_mode=True)
    orig = "System runs on port 8080."
    clean_rev = "The system runs on port 8080."
    res = reviewer.review(orig, clean_rev)
    assert res.decision == "Accept"
    assert res.is_offline

    # Attempting to mutate protected number 8080 must trigger Reject
    bad_rev = "The system runs on port 9090."
    res_bad = reviewer.review(orig, bad_rev)
    assert res_bad.decision == "Reject"


def test_reviewer_rejection_reverts_content():
    """Verify that if the reviewer rejects an edit, the original content is retained."""
    orig = "Original technical content."
    doc = make_doc(orig)

    class MockRejectReviewer:
        def review(self, o, r):
            from md_audit.llm import ReviewResult
            return ReviewResult(
                decision="Reject",
                reason="Unwarranted semantic drift",
                naturalness_improved=False,
                meaning_changed=True,
                reviewer_model="mock-critic",
            )

    engine = EditorialEngine(llm_reviewer=MockRejectReviewer())
    res = engine.improve_document(doc, run_review=True)
    assert res.revised_content == orig
    assert res.changes_count == 0


def test_reviewer_unavailable_flags_unreviewed():
    """Verify that if reviewer fails, it is marked as Unreviewed rather than pretending it passed."""
    reviewer = LLMReviewer(api_key="", offline_mode=False)
    res = reviewer.review("orig", "rev")
    assert res.decision == "Unreviewed"
    assert "Reviewer skipped" in res.reason


def test_configuration_portability():
    """Verify that default config and rules can be resolved from anywhere."""
    cfg_path = get_default_config_path()
    assert cfg_path.exists()
    assert cfg_path.name == "default_config.yaml"

    rules_dir = get_default_rules_dir()
    assert rules_dir.exists()
    assert any(rules_dir.glob("*.yaml"))

    loaded = load_config()
    assert "scoring_weights" in loaded


def test_cli_improve_llm_and_review(tmp_path: Path, capsys):
    """Test CLI improve with --llm, --review, and --offline."""
    rev_dir = tmp_path / "rev_offline"
    ret = main([
        "improve",
        "fixtures",
        "--llm",
        "--mode", "balanced",
        "--review",
        "--offline",
        "--output", str(rev_dir),
    ])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Engine mode: LLM (balanced) [offline-simulation]" in captured
    assert "Reviewer: Enabled" in captured
    assert "Editorial Summary:" in captured
