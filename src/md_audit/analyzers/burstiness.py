"""Sentence length variation (burstiness) and readability metrics analyzer."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

from ..scanner import ScannedDocument
from .deterministic import Finding


@dataclass
class BurstinessMetrics:
    """Readability and sentence rhythm metrics."""
    sentence_count: int
    mean_length: float
    std_length: float
    coefficient_of_variation: float  # std / mean (burstiness)
    flesch_reading_ease: float
    findings: list[Finding]


def count_syllables(word: str) -> int:
    """Heuristic syllable counter for English words."""
    word = word.lower().strip()
    if not word:
        return 1
    if len(word) <= 3:
        return 1
    # Remove trailing 'e'
    if word.endswith("e") and not word.endswith("le"):
        word = word[:-1]
    vowel_groups = re.findall(r"[aeiouy]+", word)
    return max(1, len(vowel_groups))


def extract_sentences(prose_lines: Sequence[str]) -> list[str]:
    """Extract individual sentences from prose lines, ignoring tables and headers."""
    sentences: list[str] = []

    for line in prose_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip markdown headers and table rows
        if stripped.startswith("#") or stripped.startswith("|"):
            continue

        # If it's a list item, strip the bullet marker
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            cleaned_line = re.sub(r"^[-*+\d.]+\s+", "", stripped)
            # Split list item on punctuation if multi-sentence
            subs = re.split(r"(?<=[.!?])\s+", cleaned_line)
            for s in subs:
                s_words = re.findall(r"\b[A-Za-z0-9_-]+\b", s)
                if len(s_words) >= 3:
                    sentences.append(s.strip())
            continue

        # Regular prose line/paragraph
        subs = re.split(r"(?<=[.!?])\s+", stripped)
        for s in subs:
            s_words = re.findall(r"\b[A-Za-z0-9_-]+\b", s)
            if len(s_words) >= 3:
                sentences.append(s.strip())

    return sentences


def analyze_burstiness(
    doc: ScannedDocument,
    min_cv: float = 0.40,
    target_fre: float = 60.0,
) -> BurstinessMetrics:
    """
    Calculate sentence variation (burstiness) and readability metrics.
    Emits findings if sentence structures are overly uniform.
    """
    sentences = extract_sentences(doc.prose_lines)
    findings: list[Finding] = []

    if not sentences:
        return BurstinessMetrics(
            sentence_count=0,
            mean_length=0.0,
            std_length=0.0,
            coefficient_of_variation=1.0,
            flesch_reading_ease=70.0,
            findings=[],
        )

    lengths = [len(re.findall(r"\b[A-Za-z0-9_-]+\b", s)) for s in sentences]
    n = len(lengths)
    mean_len = sum(lengths) / n

    if n > 1:
        variance = sum((x - mean_len) ** 2 for x in lengths) / (n - 1)
        std_len = math.sqrt(variance)
        cv = (std_len / mean_len) if mean_len > 0 else 0.0
    else:
        std_len = 0.0
        cv = 1.0

    # Calculate Flesch Reading Ease
    total_words = sum(lengths)
    all_words = re.findall(r"\b[A-Za-z]+\b", " ".join(sentences))
    total_syllables = sum(count_syllables(w) for w in all_words) if all_words else total_words

    words_per_sentence = total_words / n if n > 0 else 1.0
    syllables_per_word = total_syllables / len(all_words) if all_words else 1.0

    fre = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    fre = max(0.0, min(100.0, fre))

    # AI signature: very uniform sentence lengths (low CV) across sustained prose
    if n >= 6 and cv < min_cv:
        findings.append(
            Finding(
                file_path=doc.path,
                line_number=1,
                column=1,
                rule_id="readability.low_burstiness",
                category="readability",
                severity="warning",
                matched_text=f"Sentence CV: {cv:.2f} (std: {std_len:.1f}, mean: {mean_len:.1f})",
                explanation=(
                    f"Overly uniform sentence structures (burstiness CV: {cv:.2f} < {min_cv:.2f}). "
                    "Sentences are all roughly the same length, a common fingerprint of machine-generated text."
                ),
                suggested_improvement="Vary your rhythm: mix short punchy sentences (3-7 words) with occasional complex sentences.",
            )
        )

    # Readability warning for extremely dense prose with long sentences
    if fre < 25.0 and mean_len > 24.0 and n >= 4:
        findings.append(
            Finding(
                file_path=doc.path,
                line_number=1,
                column=1,
                rule_id="readability.dense_prose",
                category="readability",
                severity="suggestion",
                matched_text=f"Flesch Reading Ease: {fre:.1f}",
                explanation=f"Text readability is very dense (Flesch score: {fre:.1f}/100, avg sentence: {mean_len:.1f} words).",
                suggested_improvement="Simplify vocabulary or break long compound sentences into shorter units.",
            )
        )

    return BurstinessMetrics(
        sentence_count=n,
        mean_length=round(mean_len, 2),
        std_length=round(std_len, 2),
        coefficient_of_variation=round(cv, 2),
        flesch_reading_ease=round(fre, 1),
        findings=findings,
    )
