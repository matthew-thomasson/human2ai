"""Evaluation harness for measuring detection performance on controlled fixtures (Section 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .cli import run_audit
from .reporting import AuditReport, format_json_report


@dataclass
class EvaluationSample:
    """A controlled document fixture with known provenance metadata."""
    file_path: str
    provenance_type: str  # e.g., 'natural_ai_prose', 'repetitive_human_prose', 'clean_human_prose', etc.
    ground_truth_origin: str  # 'ai_generated', 'human_authored', 'mixed'
    provenance_description: str
    word_count: int = 0
    signals_detected: list[str] = field(default_factory=list)
    signals_count: int = 0
    quality_score: int = 100
    ai_patterns_score: int = 100
    rule_classified_as_ai_style: bool = False


@dataclass
class EvaluationMetrics:
    """Standard binary classification metrics computed across a fixture set."""
    total_samples: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    false_positive_rate: float
    accuracy: float
    decision_rule: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_samples": self.total_samples,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "accuracy": round(self.accuracy, 4),
            "decision_rule": self.decision_rule,
            "limitations": self.limitations,
        }


def evaluate_fixtures(
    fixtures_dir: Path | str,
    manifest: list[dict[str, str]],
    config: dict[str, Any] | None = None,
    signal_threshold: int = 2,
) -> tuple[list[EvaluationSample], EvaluationMetrics]:
    """
    Run audit across controlled fixtures and compute evaluation metrics.

    Decision rule: A document is classified as exhibiting 'elevated AI style'
    if signals_present >= signal_threshold (default 2) OR ai_patterns_score < 90.
    """
    p_dir = Path(fixtures_dir).resolve()
    report = run_audit(target_dir=p_dir, config=config or {}, enable_model=False)

    manifest_by_name = {Path(item["file"]).name: item for item in manifest}
    samples: list[EvaluationSample] = []

    tp = fp = tn = fn = 0
    decision_rule_str = (
        f"Classified as elevated AI-style if signals_present >= {signal_threshold} "
        f"or ai_patterns_score < 90."
    )

    for doc_score in report.document_scores:
        fname = Path(doc_score.file_path).name
        meta = manifest_by_name.get(fname, {
            "provenance_type": "unknown",
            "ground_truth_origin": "unknown",
            "provenance_description": "Unlisted fixture",
        })

        ai_assessment = report.ai_style_assessments.get(
            doc_score.file_path,
            report.diagnostics_by_file.get(doc_score.file_path, {}).get("ai_style_assessment", {}),
        )

        present_signals = [
            s.get("signal_id") for s in ai_assessment.get("signals", [])
            if s.get("status") == "signal_present"
        ]

        ai_cat_score = doc_score.category_scores.get("ai_patterns", 100)
        is_flagged = (len(present_signals) >= signal_threshold) or (ai_cat_score < 90)

        gt = meta.get("ground_truth_origin", "unknown")
        # For evaluation binary classification:
        # Positive class: contains AI-generated elements ('ai_generated' or 'mixed')
        # Negative class: purely human authored ('human_authored')
        is_ai_truth = gt in {"ai_generated", "mixed"}

        if is_ai_truth and is_flagged:
            tp += 1
        elif not is_ai_truth and is_flagged:
            fp += 1
        elif not is_ai_truth and not is_flagged:
            tn += 1
        elif is_ai_truth and not is_flagged:
            fn += 1

        samples.append(
            EvaluationSample(
                file_path=doc_score.file_path,
                provenance_type=meta.get("provenance_type", "unknown"),
                ground_truth_origin=gt,
                provenance_description=meta.get("provenance_description", ""),
                word_count=doc_score.word_count,
                signals_detected=present_signals,
                signals_count=len(present_signals),
                quality_score=doc_score.overall_score,
                ai_patterns_score=ai_cat_score,
                rule_classified_as_ai_style=is_flagged,
            )
        )

    total = tp + fp + tn + fn
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    fpr = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    accuracy = ((tp + tn) / total) if total > 0 else 0.0

    metrics = EvaluationMetrics(
        total_samples=total,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        false_positive_rate=fpr,
        accuracy=accuracy,
        decision_rule=decision_rule_str,
        limitations=[
            "Evaluation metrics reflect performance on a small controlled synthetic test set.",
            "Synthetic fixtures cannot represent the full distribution of diverse human authoring styles.",
            "Classification decision rule is an experimental evaluation threshold, NOT a validated production classifier.",
            "High precision or recall on synthetic fixtures does not guarantee real-world generalization.",
        ],
    )

    return samples, metrics
