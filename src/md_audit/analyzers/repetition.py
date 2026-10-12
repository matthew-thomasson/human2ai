"""Repetition and structural cadence analyzer."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

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
    """Metrics regarding lexical and structural repetition."""
    paragraph_count: int
    repeated_phrases: list[tuple[str, int]]
    findings: list[Finding]


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
    """Detect repetitive phrasing and formulaic paragraph structures."""
    findings: list[Finding] = []
    paragraphs = extract_paragraphs(doc.prose_lines)

    # 1. Check for repetitive paragraph starter transitions
    starter_counts: Counter[str] = Counter()
    starter_lines: dict[str, int] = {}
    transition_words = {"moreover", "furthermore", "additionally", "consequently", "importantly", "notably"}

    for start_line, p_text in paragraphs:
        words = re.findall(r"\b[A-Za-z]+\b", p_text)
        if words:
            first_word = words[0].lower()
            if first_word in transition_words:
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

    return RepetitionMetrics(
        paragraph_count=len(paragraphs),
        repeated_phrases=repeated_phrases,
        findings=findings,
    )
