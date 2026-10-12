"""Tests for AI-style detection enhancements (M2: Enhancements A, B, C, D)."""

from __future__ import annotations

from pathlib import Path
import pytest

from md_audit.ai_style import generate_ai_style_assessment
from md_audit.analyzers.deterministic import DeterministicAnalyzer
from md_audit.analyzers.model_evaluator import ModelEvaluator
from md_audit.analyzers.sections import (
    extract_detailed_paragraphs,
    extract_rolling_windows,
    extract_sentences_with_lines,
    split_sections_by_headings,
)
from md_audit.analyzers.structural import (
    analyze_structural_signals,
    detect_excessive_transitional_language,
    detect_formulaic_patterns,
    detect_generic_claim_clustering,
    detect_low_localized_burstiness,
    detect_repeated_paragraph_openings,
    detect_repeated_paragraph_structure,
    detect_repeated_sentence_openings,
    detect_semantic_repetition,
)
from md_audit.cli import run_audit
from md_audit.reporting import format_json_report
from md_audit.scanner import ScannedDocument, scan_file


def test_section_and_paragraph_extraction(tmp_path: Path):
    doc_text = """# Section One
This is the first sentence of the section. Here is another sentence with different length. And a third sentence here.

[Explain the first requirement clearly and thoroughly.]

## Section Two
This is section two opening sentence. It has clear and descriptive prose. And concludes naturally.
"""
    f = tmp_path / "test_sections.md"
    f.write_text(doc_text, encoding="utf-8")
    doc = scan_file(f)

    sections = split_sections_by_headings(doc)
    assert len(sections) == 2
    assert sections[0].heading_title == "Section One"
    assert sections[1].heading_title == "Section Two"
    assert sections[0].paragraph_count >= 1

    paras = extract_detailed_paragraphs(doc.prose_lines)
    assert len(paras) >= 2

    sents = extract_sentences_with_lines(doc.prose_lines)
    assert len(sents) >= 4


def test_structural_signals_detection(tmp_path: Path):
    # Text with deliberate formulaic patterns and repeated openings
    doc_text = """# Assignment Overview

In today's rapidly evolving digital landscape, it is important to note that recruitment plays a pivotal role in success.

[Explain the recruitment process in detail.]

[Explain the selection methods in detail.]

[Explain the evaluation metrics in detail.]

Moreover, the organisation must foster synergy. Furthermore, the organisation must foster synergy. Consequently, the team must align.
"""
    f = tmp_path / "test_signals.md"
    f.write_text(doc_text, encoding="utf-8")
    doc = scan_file(f)

    sections = split_sections_by_headings(doc)
    paras = extract_detailed_paragraphs(doc.prose_lines)
    sents = extract_sentences_with_lines(doc.prose_lines)
    windows = extract_rolling_windows(sents, window_size=5)

    signals = analyze_structural_signals(doc, sections, paras, windows, sents)
    assert len(signals) == 8

    # Repeated paragraph openings should be detected ([Explain ...])
    rep_openings = next(s for s in signals if s.signal_id == "signal.structural.repeated_paragraph_openings")
    assert rep_openings.status == "signal_present"
    assert "explain" in rep_openings.raw_measurement.get("frequent_first_words", {})

    # Formulaic patterns should be detected (landscape, plays a pivotal role)
    form_sig = next(s for s in signals if s.signal_id == "signal.structural.formulaic_patterns")
    assert form_sig.status == "signal_present"

    # Repeated paragraph structure should be detected (consecutive bracketed prompts)
    struct_sig = next(s for s in signals if s.signal_id == "signal.structural.repeated_paragraph_structure")
    assert struct_sig.status == "signal_present"

    # AI-style profile generation
    profile = generate_ai_style_assessment(doc, sections, paras, windows, signals)
    assert profile["status"] == "completed"
    assert profile["authorship_determined"] is False
    assert "disclaimer" in profile
    assert profile["signal_summary"]["signals_present"] >= 2
    assert len(profile["highlights"]) >= 1


def test_clean_human_prose_minimal_signals(tmp_path: Path):
    # Natural, idiosyncratic prose without corporate buzzwords or uniform prompts
    clean_text = """# Field Notes on Coastal Geology

We arrived at Chesil Beach just after sunrise. Heavy surf pounded the shingle bank.
The pebbles here grade systematically from pea-sized grit in the west to fist-sized stones near Portland.

Local fishermen hauled their wooden cobles above the high-water line. We unpacked the surveyor's levels
and began recording terrace heights across the storm ridge.

By noon, the tide was retreating rapidly, exposing ancient peat beds near the Fleet lagoon.
Samples were sealed in airtight jars for radiocarbon calibration at the university lab.
"""
    f = tmp_path / "clean_human.md"
    f.write_text(clean_text, encoding="utf-8")
    doc = scan_file(f)

    sections = split_sections_by_headings(doc)
    paras = extract_detailed_paragraphs(doc.prose_lines)
    sents = extract_sentences_with_lines(doc.prose_lines)
    windows = extract_rolling_windows(sents, window_size=5)

    signals = analyze_structural_signals(doc, sections, paras, windows, sents)
    present = [s for s in signals if s.status == "signal_present"]
    # Clean idiosyncratic writing should have 0 or at most 1 coincidental signal
    assert len(present) <= 1

    profile = generate_ai_style_assessment(doc, sections, paras, windows, signals)
    assert profile["authorship_determined"] is False
    assert "minimal" in profile["summary"] or len(present) == 0


def test_yaml_rules_regex_improvements(tmp_path: Path):
    # Test fixes for 'leveraging', 'unlocking our potential', 'ever-changing landscape', mid-line 'Moreover,'
    text = """# Test Improvements

Organizations are actively leveraging modern tools to succeed.
They are unlocking their full potential through thoughtful planning.
In an ever-changing landscape, flexibility matters.

First point here. Moreover, we must consider the second point.
"""
    f = tmp_path / "fixes.md"
    f.write_text(text, encoding="utf-8")
    doc = scan_file(f)

    analyzer = DeterministicAnalyzer.from_rules_directory("config/rules")
    findings = analyzer.analyze(doc)
    rule_ids = {item.rule_id for item in findings}

    assert "ai.cliche.leverage" in rule_ids
    assert "ai.cliche.unlock_potential" in rule_ids
    assert "ai.cliche.landscape" in rule_ids
    assert "transition.moreover" in rule_ids


def test_model_evaluator_offline_ai_style(tmp_path: Path):
    f = tmp_path / "sample.md"
    f.write_text("# Title\n\n[Explain the requirements.]\n\n[Describe the outcomes.]", encoding="utf-8")
    doc = scan_file(f)

    evaluator = ModelEvaluator(offline_mode=True)
    res = evaluator.evaluate(doc)

    assert res.ai_style_assessment is not None
    assert res.ai_style_assessment.execution_status == "offline_simulated"
    assert "disclaimer" in res.ai_style_assessment.to_dict()


def test_end_to_end_audit_and_json_report(tmp_path: Path):
    p = tmp_path / "audit_dir"
    p.mkdir()
    (p / "doc1.md").write_text("# Doc 1\n\nProse content for audit.", encoding="utf-8")

    report = run_audit(target_dir=p, config={}, enable_model=False)
    json_out = format_json_report(report)

    assert "ai_style_assessments" in json_out
    assert len(json_out["documents"]) == 1
    doc_json = json_out["documents"][0]
    assert "ai_style_assessment" in doc_json
    assert "sections" in doc_json
    assert doc_json["ai_style_assessment"]["authorship_determined"] is False


def test_evaluation_harness(tmp_path: Path):
    from md_audit.evaluation import evaluate_fixtures

    fix_dir = tmp_path / "fixtures"
    fix_dir.mkdir()
    (fix_dir / "sample_ai.md").write_text(
        "# AI Overview\n\nIn today's rapidly evolving landscape, it is important to note that recruitment plays a pivotal role.\n\nMoreover, we must unlock our potential.\n\n[Explain the role.]\n\n[Explain the tasks.]\n\n[Explain the tools.]",
        encoding="utf-8",
    )
    (fix_dir / "sample_human.md").write_text(
        "# Field Notes\n\nWe walked across the shingle ridge at dawn. The survey equipment worked without flaw.",
        encoding="utf-8",
    )

    manifest = [
        {
            "file": "sample_ai.md",
            "provenance_type": "natural_ai_prose",
            "ground_truth_origin": "ai_generated",
            "provenance_description": "Synthetic AI sample",
        },
        {
            "file": "sample_human.md",
            "provenance_type": "clean_human_prose",
            "ground_truth_origin": "human_authored",
            "provenance_description": "Human field notes",
        },
    ]

    samples, metrics = evaluate_fixtures(fix_dir, manifest, signal_threshold=2)
    assert len(samples) == 2
    assert metrics.total_samples == 2
    assert metrics.true_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0

