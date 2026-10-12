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


def test_reviewer_decisions_handling():
    """Verify editorial handling for each reviewer decision: Accept, Reject, Review manually, Unreviewed."""
    from md_audit.llm import ReviewResult

    orig = "In order to test the pipeline, we utilize standard scripts."
    doc = make_doc(orig)

    class MockReviewer:
        def __init__(self, decision: str):
            self.decision = decision

        def review(self, o, r):
            return ReviewResult(
                decision=self.decision,
                reason=f"Mock decision: {self.decision}",
                naturalness_improved=(self.decision == "Accept"),
                meaning_changed=(self.decision != "Accept"),
                reviewer_model="mock-reviewer",
            )

    # 1. Accept: revision accepted, improved text retained
    engine_accept = EditorialEngine(llm_reviewer=MockReviewer("Accept"))
    res_accept = engine_accept.improve_document(doc, run_review=True)
    assert res_accept.is_safe
    assert res_accept.changes_count > 0
    assert "utilize" not in res_accept.revised_content
    assert res_accept.review.decision == "Accept"

    # 2. Reject: revision rejected, original content retained
    engine_reject = EditorialEngine(llm_reviewer=MockReviewer("Reject"))
    res_reject = engine_reject.improve_document(doc, run_review=True)
    assert not res_reject.is_safe
    assert res_reject.changes_count == 0
    assert res_reject.revised_content == orig
    assert res_reject.review.decision == "Reject"

    # 3. Review manually: requires human approval, for MVP original content retained
    engine_manual = EditorialEngine(llm_reviewer=MockReviewer("Review manually"))
    res_manual = engine_manual.improve_document(doc, run_review=True)
    assert not res_manual.is_safe
    assert res_manual.changes_count == 0
    assert res_manual.revised_content == orig
    assert res_manual.review.decision == "Review manually"

    # 4. Unreviewed: unreviewed verdict, original content retained
    engine_unreviewed = EditorialEngine(llm_reviewer=MockReviewer("Unreviewed"))
    res_unreviewed = engine_unreviewed.improve_document(doc, run_review=True)
    assert not res_unreviewed.is_safe
    assert res_unreviewed.changes_count == 0
    assert res_unreviewed.revised_content == orig
    assert res_unreviewed.review.decision == "Unreviewed"


def test_mixed_folder_output_preservation_and_structure(tmp_path: Path, capsys):
    """
    Verify that EVERY input document is preserved in the revised output directory,
    including accepted, unchanged, and nested subdirectory files.
    """
    input_dir = tmp_path / "mixed_input"
    input_dir.mkdir()
    (input_dir / "sub").mkdir()

    # File 1: Has editorial improvements (will be revised)
    (input_dir / "improve_me.md").write_text("In order to proceed, we utilize the CLI.", encoding="utf-8")
    # File 2: Already clean prose (unchanged)
    (input_dir / "clean.md").write_text("# Clean Title\n\nDirect active prose without cliches.", encoding="utf-8")
    # File 3: Nested subdirectory document
    (input_dir / "sub" / "nested.md").write_text("In the digital age, software evolves rapidly.", encoding="utf-8")

    rev_dir = tmp_path / "rev_mixed"
    ret = main(["improve", str(input_dir), "--output", str(rev_dir)])
    assert ret == 0

    # Verify all 3 files exist in revised directory
    assert (rev_dir / "improve_me.md").exists()
    assert (rev_dir / "clean.md").exists()
    assert (rev_dir / "sub" / "nested.md").exists()

    # Clean file must be preserved byte-for-byte
    assert (rev_dir / "clean.md").read_text(encoding="utf-8") == (input_dir / "clean.md").read_text(encoding="utf-8")

    # Improved file must contain improved prose
    rev_content = (rev_dir / "improve_me.md").read_text(encoding="utf-8")
    assert "To proceed" in rev_content or "use the CLI" in rev_content
    assert "utilize" not in rev_content


def test_compare_aborts_on_missing_files(tmp_path: Path, capsys):
    """Verify that compare detects missing files, prints them, and exits with code 1."""
    orig_dir = tmp_path / "orig_cmp"
    orig_dir.mkdir()
    (orig_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
    (orig_dir / "doc2.md").write_text("# Doc 2", encoding="utf-8")

    rev_dir = tmp_path / "rev_cmp"
    rev_dir.mkdir()
    (rev_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
    # doc2.md is missing from revised directory!

    ret = main(["compare", str(orig_dir), str(rev_dir)])
    assert ret == 1
    err = capsys.readouterr().err
    assert "Missing files detected in revised directory!" in err
    assert "doc2.md" in err


def test_model_evaluator_long_document_chunking():
    """Verify that ModelEvaluator evaluates complete long documents beyond 8,000 characters."""
    from md_audit.analyzers.model_evaluator import ModelEvaluator

    # Generate a long Markdown document (> 10,000 characters)
    # Section 1 is ~9,500 characters of clean prose (past 8,000 char mark)
    sec1 = "# Section 1\n\n" + ("This is an informative paragraph discussing systems architecture.\n\n" * 140)
    # Section 2 is placed well beyond the 8,000 char mark and contains AI cliches
    sec2 = "## Section 2: Technical Claims\n\nIn today's fast-paced digital landscape, this system stands as a testament to modern engineering.\n\n"
    sec3 = "### Section 3: Summary\n\n" + ("The performance metrics confirm our low-latency design.\n\n" * 40)

    full_text = sec1 + sec2 + sec3
    assert len(full_text) > 10000
    assert len(sec1) > 8000

    doc = make_doc(full_text, path="long_doc.md")
    evaluator = ModelEvaluator(offline_mode=True)
    result = evaluator.evaluate(doc)

    # Must be evaluated across multiple sections
    assert "across" in result.critique_summary
    assert "Section" in result.critique_summary

    # Weaknesses beyond character 8,000 must be identified!
    weakness_quotes = [w.quote for w in result.weaknesses]
    assert any("in today's" in q for q in weakness_quotes)
    assert any("stands as a testament" in q for q in weakness_quotes)


def test_cli_improve_machine_readable_json(tmp_path: Path, capsys):
    """Verify that improve --format json and --output-report produce structured output."""
    import json
    report_file = tmp_path / "improve_report.json"
    rev_dir = tmp_path / "rev_json"

    ret = main([
        "improve",
        "fixtures/good_technical.md",
        "--output", str(rev_dir),
        "--format", "json",
        "--output-report", str(report_file),
    ])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "summary" in data
    assert "documents" in data
    assert len(data["documents"]) == 1
    assert data["documents"][0]["file"] == "good_technical.md"
    assert data["documents"][0]["status"] == "unchanged"

    # Verify report written to file
    assert report_file.exists()
    file_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert file_data["files_processed"] == 1


def test_cli_compare_machine_readable_json(tmp_path: Path, capsys):
    """Verify that compare --format json produces structured comparison data."""
    import json
    rev_dir = tmp_path / "rev_cmp"
    main(["improve", "fixtures/good_technical.md", "--output", str(rev_dir)])
    capsys.readouterr()  # Flush stdout from improve call

    ret = main([
        "compare",
        "fixtures/good_technical.md",
        str(rev_dir),
        "--format", "json",
    ])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "scores" in data
    assert "before" in data["scores"]
    assert "after" in data["scores"]
    assert "category_scores" in data


