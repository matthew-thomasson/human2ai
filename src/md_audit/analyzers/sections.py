"""Multi-level Markdown structure analyzer (Document, Section, Paragraph, Rolling Window)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..scanner import ScannedDocument
from .burstiness import count_syllables
from .deterministic import Finding


@dataclass
class ParagraphInfo:
    """Paragraph-level analysis unit."""
    index: int
    start_line: int
    end_line: int
    text: str
    word_count: int
    sentence_count: int
    first_word: str
    opening_phrase: str
    sufficient_text: bool
    applicability_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraph_index": self.index,
            "line_range": [self.start_line, self.end_line],
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "first_word": self.first_word,
            "opening_phrase": self.opening_phrase,
            "sufficient_text": self.sufficient_text,
            "applicability_reason": self.applicability_reason,
        }


@dataclass
class RollingWindowInfo:
    """Rolling sentence window analysis unit (typically 5 sentences)."""
    window_index: int
    start_line: int
    end_line: int
    sentence_count: int
    mean_length: float
    std_length: float
    coefficient_of_variation: float
    flesch_reading_ease: float
    sufficient_text: bool
    low_burstiness_detected: bool  # CV < 0.25

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "line_range": [self.start_line, self.end_line],
            "sentence_count": self.sentence_count,
            "mean_sentence_length": round(self.mean_length, 2),
            "std_sentence_length": round(self.std_length, 2),
            "coefficient_of_variation": round(self.coefficient_of_variation, 2),
            "flesch_reading_ease": round(self.flesch_reading_ease, 1),
            "sufficient_text": self.sufficient_text,
            "low_burstiness_detected": self.low_burstiness_detected,
        }


@dataclass
class SectionInfo:
    """Markdown section analysis unit respecting heading hierarchy."""
    index: int
    heading_title: str
    heading_level: int
    start_line: int
    end_line: int
    word_count: int
    sentence_count: int
    paragraph_count: int
    mean_sentence_length: float
    std_sentence_length: float
    coefficient_of_variation: float
    flesch_reading_ease: float
    sufficient_text: bool
    applicability_reason: str | None
    repeated_openings: list[dict[str, Any]] = field(default_factory=list)
    findings_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_index": self.index,
            "heading_title": self.heading_title,
            "heading_level": self.heading_level,
            "line_range": [self.start_line, self.end_line],
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "paragraph_count": self.paragraph_count,
            "mean_sentence_length": round(self.mean_sentence_length, 2),
            "std_sentence_length": round(self.std_sentence_length, 2),
            "coefficient_of_variation": round(self.coefficient_of_variation, 2),
            "flesch_reading_ease": round(self.flesch_reading_ease, 1),
            "sufficient_text": self.sufficient_text,
            "applicability_reason": self.applicability_reason,
            "repeated_openings": self.repeated_openings,
            "findings_count": self.findings_count,
        }


def extract_sentences_with_lines(prose_lines: Sequence[str]) -> list[tuple[int, str]]:
    """Extract individual sentences preserving their starting line numbers."""
    sentences_with_lines: list[tuple[int, str]] = []

    for idx, line in enumerate(prose_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            continue

        cleaned_line = stripped
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            cleaned_line = re.sub(r"^[-*+\d.]+\s+", "", stripped)

        subs = re.split(r"(?<=[.!?])\s+", cleaned_line)
        for s in subs:
            s_words = re.findall(r"\b[A-Za-z0-9_-]+\b", s)
            if len(s_words) >= 3:
                sentences_with_lines.append((idx, s.strip()))

    return sentences_with_lines


def extract_detailed_paragraphs(prose_lines: Sequence[str]) -> list[ParagraphInfo]:
    """Extract paragraphs with exact start/end line bounds, words, and opening phrases."""
    paragraphs: list[ParagraphInfo] = []
    current_lines: list[str] = []
    start_line = 1
    p_idx = 1

    for idx, line in enumerate(prose_lines, start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "-", "*", ">", "|")):
            if not current_lines:
                start_line = idx
            current_lines.append(stripped)
        else:
            if current_lines:
                p_text = " ".join(current_lines)
                words = re.findall(r"\b[A-Za-z0-9_-]+\b", p_text)
                first_w = words[0].lower() if words else ""
                open_phrase = " ".join(words[:3]) if len(words) >= 3 else " ".join(words)

                # Sentence count in paragraph
                subs = [s for s in re.split(r"(?<=[.!?])\s+", p_text) if len(re.findall(r"\b\w+\b", s)) >= 3]
                s_count = max(1, len(subs))

                sufficient = len(words) >= 15 and s_count >= 2
                reason = None if sufficient else f"Short paragraph ({len(words)} words, {s_count} sentences)"

                paragraphs.append(
                    ParagraphInfo(
                        index=p_idx,
                        start_line=start_line,
                        end_line=idx - 1,
                        text=p_text,
                        word_count=len(words),
                        sentence_count=s_count,
                        first_word=first_w,
                        opening_phrase=open_phrase,
                        sufficient_text=sufficient,
                        applicability_reason=reason,
                    )
                )
                p_idx += 1
                current_lines = []

    if current_lines:
        p_text = " ".join(current_lines)
        words = re.findall(r"\b[A-Za-z0-9_-]+\b", p_text)
        first_w = words[0].lower() if words else ""
        open_phrase = " ".join(words[:3]) if len(words) >= 3 else " ".join(words)
        subs = [s for s in re.split(r"(?<=[.!?])\s+", p_text) if len(re.findall(r"\b\w+\b", s)) >= 3]
        s_count = max(1, len(subs))
        sufficient = len(words) >= 15 and s_count >= 2
        reason = None if sufficient else f"Short paragraph ({len(words)} words, {s_count} sentences)"
        paragraphs.append(
            ParagraphInfo(
                index=p_idx,
                start_line=start_line,
                end_line=len(prose_lines),
                text=p_text,
                word_count=len(words),
                sentence_count=s_count,
                first_word=first_w,
                opening_phrase=open_phrase,
                sufficient_text=sufficient,
                applicability_reason=reason,
            )
        )

    return paragraphs


def compute_rhythm_metrics(sentences: Sequence[str]) -> tuple[float, float, float, float]:
    """Compute mean length, std length, CV, and Flesch Reading Ease for a set of sentences."""
    if not sentences:
        return 0.0, 0.0, 1.0, 70.0

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

    total_words = sum(lengths)
    all_words = re.findall(r"\b[A-Za-z]+\b", " ".join(sentences))
    total_syllables = sum(count_syllables(w) for w in all_words) if all_words else total_words

    words_per_sentence = total_words / n if n > 0 else 1.0
    syllables_per_word = total_syllables / len(all_words) if all_words else 1.0

    fre = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    fre = max(0.0, min(100.0, fre))

    return mean_len, std_len, cv, fre


def extract_rolling_windows(
    sentences_with_lines: Sequence[tuple[int, str]], window_size: int = 5
) -> list[RollingWindowInfo]:
    """Compute sliding sentence windows (e.g. 5 sentences) to detect localized cadence uniformity."""
    windows: list[RollingWindowInfo] = []
    if len(sentences_with_lines) < window_size:
        return windows

    for i in range(len(sentences_with_lines) - window_size + 1):
        window_slice = sentences_with_lines[i : i + window_size]
        start_line = window_slice[0][0]
        end_line = window_slice[-1][0]
        s_texts = [s[1] for s in window_slice]

        mean_len, std_len, cv, fre = compute_rhythm_metrics(s_texts)
        # Trigger localized low burstiness if CV < 0.25 across sustained 5-sentence window
        low_burst = cv < 0.25

        windows.append(
            RollingWindowInfo(
                window_index=i + 1,
                start_line=start_line,
                end_line=end_line,
                sentence_count=window_size,
                mean_length=mean_len,
                std_length=std_len,
                coefficient_of_variation=cv,
                flesch_reading_ease=fre,
                sufficient_text=True,
                low_burstiness_detected=low_burst,
            )
        )

    return windows


def split_sections_by_headings(doc: ScannedDocument, findings: Sequence[Finding] | None = None) -> list[SectionInfo]:
    """
    Split markdown prose into hierarchical sections based on headings (#, ##, ###).
    Computes statistical cadence, readability, and findings for each section independently.
    """
    lines = doc.prose_lines
    heading_indices: list[tuple[int, int, str]] = []  # (line_index_1_based, level, title)

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_indices.append((idx, level, title))

    # If document has no headings, whole document is a single section
    if not heading_indices:
        sentences_with_lines = extract_sentences_with_lines(lines)
        s_texts = [s[1] for s in sentences_with_lines]
        mean_len, std_len, cv, fre = compute_rhythm_metrics(s_texts)
        words = doc.word_count
        paragraphs = extract_detailed_paragraphs(lines)
        sec_findings = list(findings) if findings else []
        sufficient = words >= 30 and len(s_texts) >= 3

        return [
            SectionInfo(
                index=1,
                heading_title="(Root Document)",
                heading_level=0,
                start_line=1,
                end_line=len(lines),
                word_count=words,
                sentence_count=len(s_texts),
                paragraph_count=len(paragraphs),
                mean_sentence_length=mean_len,
                std_sentence_length=std_len,
                coefficient_of_variation=cv,
                flesch_reading_ease=fre,
                sufficient_text=sufficient,
                applicability_reason=None if sufficient else "Document too short for section stats",
                findings_count=len(sec_findings),
                findings=sec_findings,
            )
        ]

    sections: list[SectionInfo] = []
    total_lines = len(lines)

    # Check if there is an unheaded preamble before the first heading
    if heading_indices[0][0] > 1:
        preamble_lines = lines[0 : heading_indices[0][0] - 1]
        pre_sents = extract_sentences_with_lines(preamble_lines)
        s_texts = [s[1] for s in pre_sents]
        mean_len, std_len, cv, fre = compute_rhythm_metrics(s_texts)
        pre_words = sum(len(re.findall(r"\b\w+\b", l)) for l in preamble_lines)
        pre_paras = extract_detailed_paragraphs(preamble_lines)
        pre_findings = [f for f in (findings or []) if 1 <= f.line_number < heading_indices[0][0]]
        sufficient = pre_words >= 30 and len(s_texts) >= 3

        if pre_words > 0:
            sections.append(
                SectionInfo(
                    index=0,
                    heading_title="(Preamble / Frontmatter)",
                    heading_level=0,
                    start_line=1,
                    end_line=heading_indices[0][0] - 1,
                    word_count=pre_words,
                    sentence_count=len(s_texts),
                    paragraph_count=len(pre_paras),
                    mean_sentence_length=mean_len,
                    std_sentence_length=std_len,
                    coefficient_of_variation=cv,
                    flesch_reading_ease=fre,
                    sufficient_text=sufficient,
                    applicability_reason=None if sufficient else f"Short preamble ({pre_words} words)",
                    findings_count=len(pre_findings),
                    findings=pre_findings,
                )
            )

    # Process each heading section
    for i, (start_line, level, title) in enumerate(heading_indices):
        end_line = total_lines
        # Next section starts at next heading
        if i + 1 < len(heading_indices):
            end_line = heading_indices[i + 1][0] - 1

        sec_lines = lines[start_line - 1 : end_line]
        sec_sents = extract_sentences_with_lines(sec_lines)
        s_texts = [s[1] for s in sec_sents]
        mean_len, std_len, cv, fre = compute_rhythm_metrics(s_texts)
        sec_paras = extract_detailed_paragraphs(sec_lines)
        sec_words = sum(len(re.findall(r"\b\w+\b", l)) for l in sec_lines if not l.strip().startswith("#"))

        # Find findings within this section
        sec_findings = [f for f in (findings or []) if start_line <= f.line_number <= end_line]

        # Check for repeated sentence openings inside this section
        openings_count: dict[str, int] = {}
        for p in sec_paras:
            if p.first_word:
                openings_count[p.first_word] = openings_count.get(p.first_word, 0) + 1

        rep_openings = [{"word": w, "count": c} for w, c in openings_count.items() if c >= 2]

        sufficient = sec_words >= 30 and len(s_texts) >= 3
        reason = None if sufficient else f"Short section ({sec_words} words, {len(s_texts)} sentences)"

        sections.append(
            SectionInfo(
                index=i + 1,
                heading_title=title,
                heading_level=level,
                start_line=start_line,
                end_line=end_line,
                word_count=sec_words,
                sentence_count=len(s_texts),
                paragraph_count=len(sec_paras),
                mean_sentence_length=mean_len,
                std_sentence_length=std_len,
                coefficient_of_variation=cv,
                flesch_reading_ease=fre,
                sufficient_text=sufficient,
                applicability_reason=reason,
                repeated_openings=rep_openings,
                findings_count=len(sec_findings),
                findings=sec_findings,
            )
        )

    return sections
