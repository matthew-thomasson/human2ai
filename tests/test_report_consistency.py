"""Automated consistency check tests to prevent reporting discrepancies."""

import pytest
from pathlib import Path

def test_report_reconciliation():
    # Verify published experiment if present
    doc_review_dir = Path(r"C:\Users\matt\documentreview\projects\csc-jersey-learning-aim-a\output\ai-style-enhancement-01")
    if not doc_review_dir.exists():
        pytest.skip("documentreview project output not found")

    import json
    review_text = (doc_review_dir / "review.md").read_text(encoding="utf-8")
    comparison = json.loads((doc_review_dir / "comparison.json").read_text(encoding="utf-8"))
    manifest = json.loads((doc_review_dir / "execution-manifest.json").read_text(encoding="utf-8"))

    # Assert exact score agreements
    assert str(comparison["quality_scores"]["baseline_overall"]) in review_text
    assert str(comparison["quality_scores"]["injected_overall"]) in review_text
    assert str(comparison["findings_comparison"]["injected_findings_count"]) in review_text
    tokens = manifest["model_evaluation"]["total_tokens"]
    assert (str(tokens) in review_text) or (f"{tokens:,}" in review_text)

