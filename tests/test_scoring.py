"""Tests for QualityScorer and explainable scoring rubric."""

from md_audit.scoring import QualityScorer, DEFAULT_CATEGORY_WEIGHTS
from md_audit.analyzers.deterministic import Finding


def test_category_weights_sum_to_one():
    total_weight = sum(DEFAULT_CATEGORY_WEIGHTS.values())
    assert abs(total_weight - 1.0) < 1e-6


def test_clean_document_scores_perfect():
    scorer = QualityScorer()
    score = scorer.score_document(
        file_path="clean.md",
        word_count=500,
        findings=[],
    )
    assert score.overall_score == 100
    for cat_score in score.category_scores.values():
        assert cat_score == 100


def test_score_bounded_between_zero_and_hundred():
    scorer = QualityScorer()
    # Many severe findings
    findings = [
        Finding(
            file_path="bad.md",
            line_number=i,
            column=1,
            rule_id=f"rule.{i}",
            category="ai_patterns",
            severity="error",
            matched_text="bad text",
            explanation="bad",
            suggested_improvement="fix",
        )
        for i in range(100)
    ]
    score = scorer.score_document(
        file_path="bad.md",
        word_count=100,
        findings=findings,
    )
    assert 0 <= score.overall_score <= 100
    assert score.category_scores["ai_patterns"] >= 0


def test_directory_aggregation():
    scorer = QualityScorer()
    doc1 = scorer.score_document("doc1.md", word_count=900, findings=[])  # 100
    # doc2 with findings
    f = [
        Finding("doc2.md", 1, 1, "r1", "ai_patterns", "error", "txt", "msg", "sug"),
        Finding("doc2.md", 2, 1, "r2", "language_clarity", "error", "txt", "msg", "sug"),
    ]
    doc2 = scorer.score_document("doc2.md", word_count=100, findings=f)  # lower

    dir_score = scorer.aggregate_directory([doc1, doc2])
    assert dir_score.total_files == 2
    assert dir_score.total_words == 1000
    # doc1 is 900 words out of 1000, so aggregate score must be close to doc1
    assert dir_score.overall_score > doc2.overall_score
    assert dir_score.overall_score <= 100
