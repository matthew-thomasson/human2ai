"""Regression tests for execution-level diagnostics across all local analyzers."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import yaml

from md_audit.analyzers.burstiness import analyze_burstiness
from md_audit.analyzers.deterministic import DeterministicAnalyzer, Finding, Rule
from md_audit.analyzers.repetition import analyze_repetition
from md_audit.cli import get_default_rules_dir, run_audit
from md_audit.reporting import format_json_report
from md_audit.scanner import ScannedDocument, mask_markdown_prose, scan_directory
from md_audit.scoring import QualityScorer
from md_audit.validation import SemanticPreservationGate


@pytest.fixture
def sample_prose_doc(tmp_path: Path) -> ScannedDocument:
    """Targeted regression fixture with known text and predictable findings."""
    doc_file = tmp_path / "sample.md"
    content = (
        "# Sample Document\n\n"
        "In today's rapidly evolving landscape, we must delve into the strategy.\n\n"
        "We delve into the execution details as well.\n\n"
        "This stands as a testament to our team's success.\n"
    )
    doc_file.write_text(content, encoding="utf-8")
    docs = scan_directory(tmp_path)
    return docs[0]


def test_1_expected_local_components_executing(tmp_path: Path, sample_prose_doc: ScannedDocument):
    """1. Verify all expected local components execute and produce diagnostics."""
    report = run_audit(
        target_dir=tmp_path,
        config={},
        rules_dir=get_default_rules_dir(),
    )
    doc_diags = report.diagnostics_by_file.get(sample_prose_doc.path)
    assert doc_diags is not None

    expected_components = [
        "markdown_masker",
        "yaml_rule_analyzer",
        "repetition_analyzer",
        "burstiness_analyzer",
        "readability_analyzer",
        "quality_scorer",
    ]
    for comp in expected_components:
        assert comp in doc_diags
        assert doc_diags[comp]["status"] == "executed"
        assert doc_diags[comp]["reason"] is None


def test_2_valid_yaml_rules_loading():
    """2. Verify valid YAML rules load completely with explicit metadata."""
    rules_dir = get_default_rules_dir()
    analyzer = DeterministicAnalyzer.from_rules_directory(rules_dir)
    diag = analyzer.loader_diagnostics

    assert diag["rules_loaded_count"] > 30
    assert diag["rules_failed_count"] == 0
    assert len(diag["files_scanned"]) >= 6

    # Verify each loaded rule has id, category, severity, pattern, source_file
    for r in diag["rules_loaded"]:
        assert r["id"]
        assert r["category"] in {"ai_patterns", "readability", "repetition", "language_clarity", "consistency"}
        assert r["severity"] in {"error", "warning", "suggestion"}
        assert r["pattern"]
        assert r["source_file"].endswith(".yaml")


def test_3_malformed_rules_being_reported(tmp_path: Path):
    """3. Verify malformed rules and syntax errors are recorded rather than silently disappearing."""
    bad_rules_dir = tmp_path / "bad_rules"
    bad_rules_dir.mkdir()

    # File 1: Bad regex syntax
    f1 = bad_rules_dir / "bad_regex.yaml"
    f1.write_text(
        "category: ai_patterns\n"
        "rules:\n"
        "  - id: valid.rule\n"
        "    pattern: 'good_pattern'\n"
        "  - id: bad.regex.rule\n"
        "    pattern: '[unclosed_bracket'\n",
        encoding="utf-8",
    )

    # File 2: Missing pattern
    f2 = bad_rules_dir / "missing_pattern.yaml"
    f2.write_text(
        "rules:\n"
        "  - id: empty.pattern\n"
        "    message: 'no pattern'\n",
        encoding="utf-8",
    )

    # File 3: Corrupt YAML syntax
    f3 = bad_rules_dir / "corrupt.yaml"
    f3.write_text("rules: [unclosed list", encoding="utf-8")

    analyzer = DeterministicAnalyzer.from_rules_directory(bad_rules_dir)
    diag = analyzer.loader_diagnostics

    assert diag["rules_loaded_count"] == 1
    assert diag["rules_failed_count"] == 3

    failed_ids = [f.get("rule_id") for f in diag["rules_failed"]]
    assert "bad.regex.rule" in failed_ids
    assert "empty.pattern" in failed_ids

    # Confirm corrupt file was tracked
    corrupt_entry = next((f for f in diag["rules_failed"] if f["source_file"] == "corrupt.yaml"), None)
    assert corrupt_entry is not None
    assert "YAML parse error" in corrupt_entry["error"]


def test_4_per_rule_match_counts(tmp_path: Path):
    """4. Verify per-rule match counts and matched text evidence."""
    f = tmp_path / "doc.md"
    f.write_text(
        "We delve into the architecture.\n"
        "Later, we delve into the testing methodology.\n"
        "This stands as a testament to the effort.\n",
        encoding="utf-8",
    )
    docs = scan_directory(tmp_path)
    analyzer = DeterministicAnalyzer.from_rules_directory(get_default_rules_dir())
    findings = analyzer.analyze(docs[0])

    diag = analyzer.get_document_diagnostics(docs[0].path)
    rules_eval = {r["rule_id"]: r for r in diag["rules_evaluated"]}

    # ai.cliche.delve should have exactly 2 matches
    assert rules_eval["ai.cliche.delve"]["match_count"] == 2
    assert len(rules_eval["ai.cliche.delve"]["matches"]) == 2
    assert rules_eval["ai.cliche.delve"]["matches"][0]["matched_text"].lower() == "delve into"

    # ai.cliche.testament should have exactly 1 match
    assert rules_eval["ai.cliche.testament"]["match_count"] == 1

    # Unmatched rule should have 0 matches
    assert rules_eval["ai.cliche.tapestry"]["match_count"] == 0
    assert len(rules_eval["ai.cliche.tapestry"]["matches"]) == 0


def test_5_repetition_measurements_retained(tmp_path: Path):
    """5. Verify repetition measurements, paragraph counts, and thresholds are captured."""
    f = tmp_path / "rep.md"
    f.write_text(
        "Moreover, strategic workforce planning requires careful foresight.\n\n"
        "Moreover, strategic workforce planning requires strategic workforce planning and strategic workforce planning.\n",
        encoding="utf-8",
    )
    docs = scan_directory(tmp_path)
    rep_metrics = analyze_repetition(docs[0])
    diag = rep_metrics.to_diagnostics()

    assert diag["status"] == "executed"
    assert diag["paragraph_count"] == 2
    assert diag["transitions"]["counts"]["moreover"] == 2
    assert "moreover" in diag["transitions"]["triggered"]
    assert diag["transitions"]["threshold"] == 2

    # Check 3-gram repetition
    phrase_match = next((p for p in diag["repeated_phrases"] if "strategic workforce planning" in p["phrase"]), None)
    assert phrase_match is not None
    assert phrase_match["count"] == 4
    assert phrase_match["triggered"] is True


def test_6_burstiness_measurements_retained(tmp_path: Path):
    """6. Verify burstiness sentence stats and threshold comparison."""
    f = tmp_path / "burst.md"
    # 6 sentences with identical word lengths (5 words each) -> CV should be 0.0
    f.write_text(
        "This is the first sentence. "
        "This is the second sentence. "
        "This is the third sentence. "
        "This is the fourth sentence. "
        "This is the fifth sentence. "
        "This is the sixth sentence.\n",
        encoding="utf-8",
    )
    docs = scan_directory(tmp_path)
    metrics = analyze_burstiness(docs[0])
    diag = metrics.to_burstiness_diagnostics()

    assert diag["status"] == "executed"
    assert diag["sentence_count"] == 6
    assert diag["mean_sentence_length"] == 5.0
    assert diag["std_sentence_length"] == 0.0
    assert diag["coefficient_of_variation"] == 0.0
    assert diag["comparison"]["evaluated"] is True
    assert diag["comparison"]["triggered"] is True
    assert diag["findings_count"] == 1


def test_7_readability_measurements_retained(tmp_path: Path):
    """7. Verify Flesch score, underlying counts, and dense prose threshold comparison."""
    f = tmp_path / "read.md"
    f.write_text(
        "The quick brown fox jumps over the lazy dog. "
        "Simple words make reading easy for everyone.\n",
        encoding="utf-8",
    )
    docs = scan_directory(tmp_path)
    metrics = analyze_burstiness(docs[0])
    diag = metrics.to_readability_diagnostics()

    assert diag["status"] == "executed"
    assert diag["underlying_counts"]["sentence_count"] == 2
    assert diag["underlying_counts"]["total_words"] == 16
    assert diag["underlying_counts"]["words_per_sentence"] == 8.0
    assert diag["flesch_reading_ease"] > 60.0
    assert diag["dense_prose_comparison"]["evaluated"] is False  # Requires >= 4 sentences


def test_8_accurate_scoring_calculations(tmp_path: Path):
    """8. Verify complete penalty calculations by category including zero penalties and rounding."""
    f = tmp_path / "score_test.md"
    f.write_text("We delve into this. We delve into that.\n", encoding="utf-8")
    docs = scan_directory(tmp_path)

    findings = [
        Finding(
            file_path="score_test.md",
            line_number=1,
            column=1,
            rule_id="ai.cliche.delve",
            category="ai_patterns",
            severity="warning",
            matched_text="delve into",
            explanation="test",
            suggested_improvement="test",
        ),
    ]

    scorer = QualityScorer()
    doc_score = scorer.score_document(
        file_path="score_test.md",
        word_count=120,
        findings=findings,
    )
    diag = doc_score.scoring_diagnostics

    assert diag["status"] == "executed"
    assert diag["word_count"] == 120
    # scaled_denom for 120 words = 120^0.65 = 22.427
    assert diag["scaled_denominator"] > 22.0

    # ai_patterns had 1 warning (penalty 6.0)
    ai_cat = diag["categories"]["ai_patterns"]
    assert ai_cat["raw_penalty"] == 6.0
    assert ai_cat["zero_penalty"] is False
    assert ai_cat["normalized_penalty"] > 0
    assert ai_cat["final_category_score"] < 100

    # readability had 0 findings -> zero penalty
    read_cat = diag["categories"]["readability"]
    assert read_cat["raw_penalty"] == 0.0
    assert read_cat["zero_penalty"] is True
    assert read_cat["total_penalty"] == 0.0
    assert read_cat["final_category_score"] == 100

    assert doc_score.overall_score <= 100
    assert diag["overall"]["final_overall_score"] == doc_score.overall_score


def test_9_not_applicable_and_failed_states(tmp_path: Path):
    """9. Verify empty documents produce not_applicable status with explicit reason."""
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("   \n\n   \n", encoding="utf-8")

    report = run_audit(target_dir=tmp_path, config={})
    doc_diag = report.diagnostics_by_file["empty.md"]

    assert doc_diag["markdown_masker"]["status"] == "not_applicable"
    assert doc_diag["yaml_rule_analyzer"]["status"] == "not_applicable"
    assert doc_diag["repetition_analyzer"]["status"] == "not_applicable"
    assert doc_diag["burstiness_analyzer"]["status"] == "not_applicable"
    assert doc_diag["readability_analyzer"]["status"] == "not_applicable"
    assert doc_diag["quality_scorer"]["status"] == "not_applicable"

    for comp in ["yaml_rule_analyzer", "repetition_analyzer", "burstiness_analyzer"]:
        assert "Insufficient analysable text" in doc_diag[comp]["reason"]


def test_10_correct_source_line_attribution(tmp_path: Path):
    """10. Verify masked constructs preserve exact original line numbering."""
    f = tmp_path / "lines.md"
    # Line 1: frontmatter start
    # Line 2: frontmatter content
    # Line 3: frontmatter end
    # Line 4: blank
    # Line 5: HTML comment
    # Line 6: blank
    # Line 7: target finding
    f.write_text(
        "---\ntitle: Test\n---\n\n<!-- comment -->\n\nWe must delve into the plan.\n",
        encoding="utf-8",
    )
    docs = scan_directory(tmp_path)
    analyzer = DeterministicAnalyzer.from_rules_directory(get_default_rules_dir())
    findings = analyzer.analyze(docs[0])

    delve_finding = next((f for f in findings if f.rule_id == "ai.cliche.delve"), None)
    assert delve_finding is not None
    assert delve_finding.line_number == 7
    assert delve_finding.column == 9
    assert delve_finding.matched_text == "delve into"


def test_11_stable_json_serialization(tmp_path: Path, sample_prose_doc: ScannedDocument):
    """11. Verify serialization produces valid, stable JSON without serialization errors."""
    report = run_audit(target_dir=tmp_path, config={})
    json_data = format_json_report(report)

    # Must serialize and deserialize cleanly
    dumped = json.dumps(json_data, indent=2)
    reloaded = json.loads(dumped)

    assert "engine_diagnostics" in reloaded
    assert "rules_loader" in reloaded["engine_diagnostics"]
    doc_entry = reloaded["documents"][0]
    assert "diagnostics" in doc_entry
    assert "yaml_rule_analyzer" in doc_entry["diagnostics"]
    assert "scoring" in doc_entry["rubric_breakdown"] or "quality_scorer" in doc_entry["diagnostics"]


def test_12_original_document_preservation():
    """12. Verify semantic preservation gate reports exact checks run and violations."""
    gate = SemanticPreservationGate()
    orig = "We employ 250 employees by 2026-01-01. See https://example.com/team"
    revised_safe = "We retain 250 employees by 2026-01-01. See https://example.com/team"
    revised_unsafe = "We retain 100 employees by 2026-01-01. See https://example.com/team"

    # Safe pass
    res_safe = gate.validate(orig, revised_safe)
    assert res_safe.is_valid is True
    assert len(res_safe.checks_run) == 7
    assert all(c["passed"] for c in res_safe.checks_run)

    # Unsafe pass (numbers modified)
    res_unsafe = gate.validate(orig, revised_unsafe)
    assert res_unsafe.is_valid is False
    num_check = next(c for c in res_unsafe.checks_run if c["check"] == "numerical_values")
    assert num_check["passed"] is False
    assert num_check["violations_detected"] >= 1
    assert any(c.change_type == "numerical_value" for c in res_unsafe.material_changes)
