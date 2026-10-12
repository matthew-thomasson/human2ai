"""Transparent, explainable 0-100 writing quality scoring model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .analyzers.burstiness import BurstinessMetrics
from .analyzers.deterministic import Finding
from .analyzers.repetition import RepetitionMetrics

DEFAULT_CATEGORY_WEIGHTS = {
    "ai_patterns": 0.25,
    "readability": 0.20,
    "repetition": 0.20,
    "language_clarity": 0.20,
    "consistency": 0.15,
}

DEFAULT_SEVERITY_PENALTIES = {
    "error": 12.0,
    "warning": 6.0,
    "suggestion": 3.0,
}


@dataclass
class DocumentScore:
    """Document-level quality scores and rubric derivation breakdown."""
    file_path: str
    overall_score: int  # 0 to 100
    category_scores: dict[str, int]
    word_count: int
    findings_count: int
    rubric_breakdown: dict[str, str] = field(default_factory=dict)
    model_score: int | None = None  # Kept explicitly separate


@dataclass
class DirectoryScore:
    """Aggregated directory-level writing quality scores."""
    total_files: int
    total_words: int
    overall_score: int
    category_scores: dict[str, int]
    files_with_issues: int
    aggregation_method: str = "word_count_weighted_average"
    disclaimer: str = (
        "Scores reflect writing quality, stylistic clarity, and natural cadence. "
        "They do NOT represent an AI-authorship probability or detector verdict."
    )


class QualityScorer:
    """Calculates explainable, length-normalized writing quality scores."""

    def __init__(
        self,
        category_weights: dict[str, float] | None = None,
        severity_penalties: dict[str, float] | None = None,
    ):
        self.weights = category_weights or DEFAULT_CATEGORY_WEIGHTS
        self.penalties = severity_penalties or DEFAULT_SEVERITY_PENALTIES

    def score_document(
        self,
        file_path: str,
        word_count: int,
        findings: Sequence[Finding],
        burstiness: BurstinessMetrics | None = None,
        repetition: RepetitionMetrics | None = None,
        model_score: int | None = None,
    ) -> DocumentScore:
        """Calculate length-normalized 0-100 scores across 5 quality categories."""
        # Minimum effective word count prevents division explosions on tiny stubs
        effective_words = max(80, word_count)
        normalization_factor = 1000.0 / effective_words

        # Group findings by category
        cat_findings: dict[str, list[Finding]] = {cat: [] for cat in self.weights}
        for f in findings:
            cat = f.category if f.category in cat_findings else "language_clarity"
            cat_findings[cat].append(f)

        category_scores: dict[str, int] = {}
        rubric_breakdown: dict[str, str] = {}

        # Sublinear length-normalization prevents document length alone from dominating
        # Power scaling (words^0.65) ensures fair density scaling across short (100w) and long (3000w) docs
        scaled_denom = max(120, word_count) ** 0.65

        for cat, cat_list in cat_findings.items():
            # Sum weighted severity penalties
            raw_penalty = sum(self.penalties.get(f.severity, 4.0) for f in cat_list)
            normalized_penalty = (raw_penalty / scaled_denom) * 22.0

            # Special adjustments for readability
            if cat == "readability" and burstiness:
                if burstiness.sentence_count >= 5 and burstiness.coefficient_of_variation < 0.22:
                    normalized_penalty += 10.0

            final_cat_score = max(0, min(100, int(round(100.0 - normalized_penalty))))
            category_scores[cat] = final_cat_score

            rubric_breakdown[cat] = (
                f"Base 100 - {normalized_penalty:.1f} penalty "
                f"({len(cat_list)} issues normalized for {word_count} words) = {final_cat_score}/100"
            )

        # Calculate weighted overall score
        overall_float = sum(
            category_scores[cat] * self.weights.get(cat, 0.20)
            for cat in self.weights
        )
        overall_score = max(0, min(100, int(round(overall_float))))

        return DocumentScore(
            file_path=file_path,
            overall_score=overall_score,
            category_scores=category_scores,
            word_count=word_count,
            findings_count=len(findings),
            rubric_breakdown=rubric_breakdown,
            model_score=model_score,
        )

    def aggregate_directory(
        self,
        doc_scores: Sequence[DocumentScore],
    ) -> DirectoryScore:
        """
        Aggregate file scores into an overall directory quality assessment
        using word-count-weighted averaging.
        """
        if not doc_scores:
            return DirectoryScore(
                total_files=0,
                total_words=0,
                overall_score=100,
                category_scores={cat: 100 for cat in self.weights},
                files_with_issues=0,
            )

        total_words = sum(doc.word_count for doc in doc_scores)
        files_with_issues = sum(1 for doc in doc_scores if doc.findings_count > 0)

        if total_words == 0:
            # Fall back to arithmetic mean if no words
            overall = int(round(sum(d.overall_score for d in doc_scores) / len(doc_scores)))
            agg_cats = {
                cat: int(round(sum(d.category_scores[cat] for d in doc_scores) / len(doc_scores)))
                for cat in self.weights
            }
        else:
            overall = int(
                round(sum(d.overall_score * d.word_count for d in doc_scores) / total_words)
            )
            agg_cats = {
                cat: int(
                    round(sum(d.category_scores[cat] * d.word_count for d in doc_scores) / total_words)
                )
                for cat in self.weights
            }

        return DirectoryScore(
            total_files=len(doc_scores),
            total_words=total_words,
            overall_score=max(0, min(100, overall)),
            category_scores=agg_cats,
            files_with_issues=files_with_issues,
        )
