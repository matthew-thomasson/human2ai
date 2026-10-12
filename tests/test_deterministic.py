"""Tests for deterministic style and AI-tell rule analysis."""

from pathlib import Path
from md_audit.analyzers.deterministic import DeterministicAnalyzer
from md_audit.scanner import ScannedDocument, mask_markdown_prose, count_prose_words


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


def test_ai_cliches_detected():
    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    text = (
        "# Title\n"
        "Let us delve into this topic.\n"
        "This achievement stands as a testament to engineering.\n"
        "It plays a pivotal role in the landscape.\n"
    )
    doc = make_doc(text)
    findings = analyzer.analyze(doc)

    rule_ids = [f.rule_id for f in findings]
    assert "ai.cliche.delve" in rule_ids
    assert "ai.cliche.testament" in rule_ids
    assert "ai.cliche.pivotal_role" in rule_ids


def test_code_blocks_not_flagged():
    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    text = (
        "# Code sample\n"
        "```python\n"
        "# This should never be flagged\n"
        "def delve_into_data():\n"
        "    return 'stands as a testament'\n"
        "```\n"
        "Real prose is clean here.\n"
    )
    doc = make_doc(text)
    findings = analyzer.analyze(doc)

    rule_ids = [f.rule_id for f in findings]
    assert "ai.cliche.delve" not in rule_ids
    assert "ai.cliche.testament" not in rule_ids


def test_formulaic_structure():
    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    text = (
        "In today's fast-paced world, speed matters.\n"
        "It's not just a product, it's a movement.\n"
        "In conclusion, only time will tell.\n"
    )
    doc = make_doc(text)
    findings = analyzer.analyze(doc)

    rule_ids = [f.rule_id for f in findings]
    assert "structure.intro.fast_paced" in rule_ids
    assert "structure.negative_parallelism" in rule_ids
    assert "structure.closer.formulaic" in rule_ids


def test_wordy_constructions():
    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    text = "We ran the test in order to verify functionality, due to the fact that errors occurred."
    doc = make_doc(text)
    findings = analyzer.analyze(doc)

    rule_ids = [f.rule_id for f in findings]
    assert "clarity.wordy.in_order_to" in rule_ids
    assert "clarity.wordy.due_to_the_fact" in rule_ids


def test_inconsistent_terminology():
    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    text = "Our front-end is written in React, while the other frontend is in Vue."
    doc = make_doc(text)
    findings = analyzer.analyze(doc)

    rule_ids = [f.rule_id for f in findings]
    assert "consistency.terminology" in rule_ids
