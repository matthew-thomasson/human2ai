"""Repetition and structural cadence analyzer."""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..scanner import ScannedDocument
from .deterministic import Finding

COMMON_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "is", "are", "was", "were", "it", "this", "that",
    "these", "those", "be", "been", "have", "has", "had", "do", "does", "did",
    "will", "would", "should", "could", "can", "may", "might", "must", "if", "then",
}


@dataclass
class RepetitionMetrics:
    """Metrics regarding lexical and structural repetition with full execution diagnostics."""
    paragraph_count: int
    repeated_phrases: list[tuple[str, int]]
    findings: list[Finding]
    transitions: dict[str, int] = field(default_factory=dict)
    sentence_openings: list[dict[str, Any]] = field(default_factory=list)
    transition_threshold: int = 2
    n_gram_threshold: int = 3
    status: str = "executed"
    reason: str | None = None
    checks_performed: int = 0
    checks_triggered: int = 0
    duration_ms: float = 0.0

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "component": "repetition_analyzer",
            "implementation": "md_audit.analyzers.repetition.analyze_repetition",
            "version": "1.0.0",
            "status": self.status,
            "reason": self.reason,
            "paragraph_count": self.paragraph_count,
            "transitions": {
                "threshold": self.transition_threshold,
                "counts": self.transitions,
                "triggered": [t for t, c in self.transitions.items() if c >= self.transition_threshold],
            },
            "repeated_phrases": [
                {
                    "phrase": phrase,
                    "count": cnt,
                    "threshold": self.n_gram_threshold,
                    "triggered": cnt >= self.n_gram_threshold,
                }
                for phrase, cnt in self.repeated_phrases
            ],
            "sentence_openings": self.sentence_openings,
            "checks_performed": self.checks_performed,
            "checks_triggered": self.checks_triggered,
            "findings_count": len(self.findings),
            "duration_ms": self.duration_ms,
            "errors": [],
            "warnings": [],
        }


def extract_paragraphs(prose_lines: Sequence[str]) -> list[tuple[int, str]]:
    """Extract distinct non-empty paragraphs along with starting line numbers."""
    paragraphs: list[tuple[int, str]] = []
    current_lines: list[str] = []
    start_line = 1

    for idx, line in enumerate(prose_lines, start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "-", "*", ">", "|")):
            if not current_lines:
                start_line = idx
            current_lines.append(stripped)
        else:
            if current_lines:
                paragraphs.append((start_line, " ".join(current_lines)))
                current_lines = []

    if current_lines:
        paragraphs.append((start_line, " ".join(current_lines)))

    return paragraphs


def analyze_repetition(doc: ScannedDocument) -> RepetitionMetrics:
    """Detect repetitive phrasing and formulaic paragraph structures with diagnostics."""
    t0 = time.perf_counter()
    findings: list[Finding] = []
    paragraphs = extract_paragraphs(doc.prose_lines)

    transition_words = ["moreover", "furthermore", "additionally", "consequently", "importantly", "notably"]
    starter_counts: dict[str, int] = {t: 0 for t in transition_words}
    starter_lines: dict[str, int] = {}
    sentence_openings: list[dict[str, Any]] = []

    if not paragraphs or doc.word_count == 0:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return RepetitionMetrics(
            paragraph_count=0,
            repeated_phrases=[],
            findings=[],
            transitions=starter_counts,
            sentence_openings=[],
            transition_threshold=2,
            n_gram_threshold=3,
            status="not_applicable",
            reason="Insufficient analysable text (0 paragraphs or words)",
            checks_performed=0,
            checks_triggered=0,
            duration_ms=elapsed_ms,
        )

    # 1. Check for repetitive paragraph starter transitions
    for start_line, p_text in paragraphs:
        words = re.findall(r"\b[A-Za-z]+\b", p_text)
        if words:
            first_word = words[0].lower()
            opening_entry = {"line": start_line, "first_word": first_word}
            if len(words) >= 2:
                opening_entry["opening_words"] = f"{words[0]} {words[1]}"
            sentence_openings.append(opening_entry)

            if first_word in starter_counts:
                starter_counts[first_word] += 1
                if first_word not in starter_lines:
                    starter_lines[first_word] = start_line

    for trans, count in starter_counts.items():
        if count >= 2:
            findings.append(
                Finding(
                    file_path=doc.path,
                    line_number=starter_lines[trans],
                    column=1,
                    rule_id="repetition.transition_clustering",
                    category="repetition",
                    severity="warning",
                    matched_text=f"'{trans.capitalize()}' used {count} times to begin paragraphs",
                    explanation=f"Repetitive use of formal transition word '{trans}' across multiple paragraphs.",
                    suggested_improvement="Omit the transition word or link ideas through direct narrative flow.",
                )
            )

    # 2. Check for overused 3-gram phrases
    words = [w.lower() for w in re.findall(r"\b[a-z]{3,}\b", doc.prose_content)]
    filtered_words = [w for w in words if w not in COMMON_STOPWORDS]

    tri_grams = [
        f"{filtered_words[i]} {filtered_words[i+1]} {filtered_words[i+2]}"
        for i in range(len(filtered_words) - 2)
    ]
    tri_counts = Counter(tri_grams)
    repeated_phrases: list[tuple[str, int]] = []

    for phrase, cnt in tri_counts.most_common(5):
        if cnt >= 3:
            repeated_phrases.append((phrase, cnt))
            findings.append(
                Finding(
                    file_path=doc.path,
                    line_number=1,
                    column=1,
                    rule_id="repetition.n_gram",
                    category="repetition",
                    severity="suggestion",
                    matched_text=f"'{phrase}' appears {cnt} times",
                    explanation=f"Phrase '{phrase}' is repeated {cnt} times in close succession.",
                    suggested_improvement="Vary your word choice or eliminate redundant mentions.",
                )
            )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    checks_performed = len(transition_words) + len(tri_counts)
    checks_triggered = len(findings)

    return RepetitionMetrics(
        paragraph_count=len(paragraphs),
        repeated_phrases=repeated_phrases,
        findings=findings,
        transitions=starter_counts,
        sentence_openings=sentence_openings,
        transition_threshold=2,
        n_gram_threshold=3,
        status="executed",
        reason=None,
        checks_performed=checks_performed,
        checks_triggered=checks_triggered,
        duration_ms=elapsed_ms,
    )
