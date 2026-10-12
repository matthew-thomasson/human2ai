"""Structural and formulaic writing signals analyzer (Enhancement B)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..scanner import ScannedDocument
from .sections import (
    ParagraphInfo,
    RollingWindowInfo,
    SectionInfo,
    extract_detailed_paragraphs,
    extract_rolling_windows,
    extract_sentences_with_lines,
    split_sections_by_headings,
)

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "cannot", "could", "did", "do", "does", "doing", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "were",
    "weren't", "what", "when", "where", "which", "while", "who", "whom", "why", "with", "won't",
    "would", "you", "your", "yours", "yourself", "yourselves",
}

TRANSITIONAL_MARKERS = [
    "moreover", "furthermore", "consequently", "additionally", "in addition",
    "notably", "importantly", "ultimately", "therefore", "thus", "hence",
    "conversely", "as a result", "in summary", "to summarize", "in essence",
]

GENERIC_BUZZWORDS = {
    "holistic", "synergy", "pivotal", "transformational", "comprehensive",
    "robust", "seamlessly", "seamless", "optimize", "foster", "leverage",
    "empower", "paramount", "revolutionize", "dynamic", "cutting-edge",
    "cornerstone", "vibrant", "tapestry", "multifaceted", "interplay",
}


@dataclass
class StructuralSignal:
    """Standardized representation of a detected or evaluated structural writing signal."""
    signal_id: str
    name: str
    description: str
    implementation_reference: str
    status: str  # "signal_present", "no_measurable_signal", "insufficient_evidence", "analysis_not_applicable"
    raw_measurement: Any
    threshold: str
    supporting_text: list[str]
    source_location: dict[str, Any]
    limitations: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "name": self.name,
            "description": self.description,
            "implementation_reference": self.implementation_reference,
            "status": self.status,
            "raw_measurement": self.raw_measurement,
            "threshold": self.threshold,
            "supporting_text": self.supporting_text,
            "source_location": self.source_location,
            "limitations": self.limitations,
        }


def detect_repeated_paragraph_openings(paragraphs: list[ParagraphInfo]) -> StructuralSignal:
    """Detect repetitive paragraph opening words or phrases across the document."""
    signal_id = "signal.structural.repeated_paragraph_openings"
    name = "Repeated Paragraph Openings"
    desc = "Identifies clusters of paragraphs starting with identical leading words or imperative prompt stems."
    impl_ref = "md_audit.analyzers.structural.detect_repeated_paragraph_openings"
    limitations = (
        "Instructional templates, structured rubrics, and formal specifications frequently use "
        "deliberate uniform imperatives (e.g. 'Explain...', 'Describe...')."
    )
    threshold = "Count >= 3 identical first words or count >= 2 identical opening phrases across paragraphs."

    if len(paragraphs) < 3:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"paragraph_count": len(paragraphs)},
            threshold=threshold,
            supporting_text=[],
            source_location={"paragraph_count": len(paragraphs)},
            limitations=limitations,
        )

    # Clean leading brackets or symbols from first words for prompt detection (e.g. '[Explain' -> 'explain')
    word_counts: dict[str, list[ParagraphInfo]] = {}
    phrase_counts: dict[str, list[ParagraphInfo]] = {}

    for p in paragraphs:
        cleaned_first = re.sub(r"^[\[\(#*\-_]+", "", p.first_word).strip().lower()
        if cleaned_first:
            word_counts.setdefault(cleaned_first, []).append(p)
        cleaned_phrase = re.sub(r"^[\[\(#*\-_]+", "", p.opening_phrase).strip().lower()
        if cleaned_phrase and len(cleaned_phrase.split()) >= 2:
            phrase_counts.setdefault(cleaned_phrase, []).append(p)

    frequent_words = {w: ps for w, ps in word_counts.items() if len(ps) >= 3}
    frequent_phrases = {ph: ps for ph, ps in phrase_counts.items() if len(ps) >= 2}

    if frequent_words or frequent_phrases:
        supporting: list[str] = []
        loc_paras: list[int] = []
        loc_lines: list[list[int]] = []

        for w, ps in frequent_words.items():
            for p in ps:
                supporting.append(f"P{p.index} (L{p.start_line}): starts with '{w}' -> '{p.opening_phrase}'")
                loc_paras.append(p.index)
                loc_lines.append([p.start_line, p.end_line])

        for ph, ps in frequent_phrases.items():
            if ph not in frequent_words:
                for p in ps:
                    supporting.append(f"P{p.index} (L{p.start_line}): opening phrase '{ph}'")
                    loc_paras.append(p.index)
                    loc_lines.append([p.start_line, p.end_line])

        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "frequent_first_words": {w: len(ps) for w, ps in frequent_words.items()},
                "frequent_opening_phrases": {ph: len(ps) for ph, ps in frequent_phrases.items()},
            },
            threshold=threshold,
            supporting_text=supporting[:8],
            source_location={"paragraphs": sorted(list(set(loc_paras))), "line_ranges": loc_lines[:8]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"max_first_word_count": max((len(ps) for ps in word_counts.values()), default=0)},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_repeated_sentence_openings(sentences_with_lines: list[tuple[int, str]]) -> StructuralSignal:
    """Detect repetitive sentence-initial tokens or phrases across proximate sentences."""
    signal_id = "signal.structural.repeated_sentence_openings"
    name = "Repeated Sentence Openings"
    desc = "Detects repetitive sentence-initial tokens or phrases (2-3 words) across proximate sentences."
    impl_ref = "md_audit.analyzers.structural.detect_repeated_sentence_openings"
    limitations = "Technical procedures or requirements documents frequently repeat opening nouns or verb structures."
    threshold = "Count >= 3 occurrences of identical 2-3 word sentence opening or >= 2 in consecutive sentences."

    if len(sentences_with_lines) < 5:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"sentence_count": len(sentences_with_lines)},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    openings: dict[str, list[tuple[int, str]]] = {}
    prev_opening = ""
    consecutive_hits: list[tuple[int, str]] = []

    for line_no, text in sentences_with_lines:
        words = re.findall(r"\b[A-Za-z0-9_-]+\b", text)
        if len(words) >= 2:
            opening_2 = " ".join(words[:2]).lower()
            openings.setdefault(opening_2, []).append((line_no, text))
            if opening_2 == prev_opening:
                consecutive_hits.append((line_no, text))
            prev_opening = opening_2
        else:
            prev_opening = ""

    frequent_openings = {op: sents for op, sents in openings.items() if len(sents) >= 3}

    if frequent_openings or consecutive_hits:
        supporting: list[str] = []
        loc_lines: list[int] = []

        for op, sents in frequent_openings.items():
            for line_no, s in sents:
                supporting.append(f"L{line_no}: '{op}' in \"{s[:70]}...\"")
                loc_lines.append(line_no)

        for line_no, s in consecutive_hits:
            supporting.append(f"L{line_no} (consecutive): \"{s[:70]}...\"")
            loc_lines.append(line_no)

        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "frequent_openings": {op: len(sents) for op, sents in frequent_openings.items()},
                "consecutive_repeat_count": len(consecutive_hits),
            },
            threshold=threshold,
            supporting_text=supporting[:8],
            source_location={"lines": sorted(list(set(loc_lines)))[:12]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"max_opening_repeat": max((len(s) for s in openings.values()), default=0)},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_excessive_transitional_language(doc: ScannedDocument, sections: list[SectionInfo]) -> StructuralSignal:
    """Identify unnatural density of formal discourse transitions."""
    signal_id = "signal.structural.excessive_transitional_language"
    name = "Excessive Transitional Language"
    desc = "Identifies an unnatural density of formal conjunctive adverbs (moreover, furthermore, consequently, etc.)."
    impl_ref = "md_audit.analyzers.structural.detect_excessive_transitional_language"
    limitations = "Academic papers and argumentative essays traditionally employ high transition density for cohesion."
    threshold = "Rate >= 15.0 transitions per 1,000 words (or >= 4 in a section < 300 words)."

    words_total = doc.word_count
    if words_total < 80:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"word_count": words_total},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    matches: list[tuple[int, str, str]] = []  # (line, marker, snippet)
    pattern = re.compile(
        r"(?i)(?:^|(?<=[.!?])\s+|[-*]\s+|\b)("
        + "|".join(re.escape(m) for m in TRANSITIONAL_MARKERS)
        + r")\b"
    )

    for idx, line in enumerate(doc.prose_lines, start=1):
        if line.strip().startswith("#") or line.strip().startswith("|"):
            continue
        for m in pattern.finditer(line):
            matched = m.group(1).lower()
            matches.append((idx, matched, line.strip()))

    total_matches = len(matches)
    rate_per_1000 = (total_matches / words_total * 1000.0) if words_total > 0 else 0.0

    # Section-level check
    section_burst = False
    flagged_sections = []
    for sec in sections:
        sec_matches = [m for m in matches if sec.start_line <= m[0] <= sec.end_line]
        if len(sec_matches) >= 4 and sec.word_count < 350:
            section_burst = True
            flagged_sections.append({"section": sec.heading_title, "matches": len(sec_matches), "words": sec.word_count})

    if rate_per_1000 >= 15.0 or section_burst:
        supporting = [f"L{m[0]}: transition '{m[1]}' in \"{m[2][:70]}...\"" for m in matches[:8]]
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "total_transitions": total_matches,
                "rate_per_1000_words": round(rate_per_1000, 2),
                "flagged_sections": flagged_sections,
            },
            threshold=threshold,
            supporting_text=supporting,
            source_location={"lines": [m[0] for m in matches[:12]]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={
            "total_transitions": total_matches,
            "rate_per_1000_words": round(rate_per_1000, 2),
        },
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_formulaic_patterns(doc: ScannedDocument) -> StructuralSignal:
    """Detect stereotypical rhetorical tropes characteristic of LLM scaffolding."""
    signal_id = "signal.structural.formulaic_patterns"
    name = "Formulaic Introduction, Transition, and Conclusion Patterns"
    desc = "Detects stereotypical rhetorical tropes characteristic of LLM scaffolding."
    impl_ref = "md_audit.analyzers.structural.detect_formulaic_patterns"
    limitations = "Standard essay rubrics, high school frameworks, or public speech scripts frequently teach formulaic tropes."
    threshold = "Count >= 1 matching formulaic pattern."

    if doc.word_count < 50:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"word_count": doc.word_count},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    PATTERNS = [
        ("Introductory fluff", re.compile(r"(?i)\b(?:in\s+today's|in\s+the\s+modern|in\s+our\s+rapidly)\s+(?:fast-paced|rapidly\s+evolving|ever-evolving|digital|competitive)\s+(?:world|landscape|era|environment)\b")),
        ("Significance puffery", re.compile(r"(?i)\bplays?\s+a\s+(?:pivotal|crucial|vital|fundamental)\s+role\b")),
        ("Throat clearing", re.compile(r"(?i)\b(?:it\s+is|it's)\s+(?:important\s+to\s+note|worth\s+noting)\s+that\b")),
        ("Delve cliché", re.compile(r"(?i)\bdelve(?:s|d|ing)?\s+into\b")),
        ("Formulaic conclusion", re.compile(r"(?i)\b(?:in\s+conclusion|to\s+summarize|to\s+sum\s+up|in\s+summary)[,:]")),
        ("Testament trope", re.compile(r"(?i)\bstands?\s+as\s+a\s+testament\s+to\b")),
        ("Unlock potential", re.compile(r"(?i)\bunlock(?:s|ed|ing)?\s+(?:the\s+)?(?:full\s+)?potential\b")),
        ("Negative parallelism", re.compile(r"(?i)\b(?:not\s+only|it's\s+not\s+just)\b[^.!?]{1,60}\b(?:but\s+also|it's\s+about)\b")),
    ]

    matches: list[tuple[int, str, str]] = []
    for idx, line in enumerate(doc.prose_lines, start=1):
        for label, pat in PATTERNS:
            for m in pat.finditer(line):
                matches.append((idx, label, m.group(0)))

    if matches:
        supporting = [f"L{m[0]}: [{m[1]}] '{m[2]}'" for m in matches[:8]]
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={"matches_count": len(matches), "categories": list(set(m[1] for m in matches))},
            threshold=threshold,
            supporting_text=supporting,
            source_location={"lines": [m[0] for m in matches[:12]]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"matches_count": 0},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_repeated_paragraph_structure(paragraphs: list[ParagraphInfo]) -> StructuralSignal:
    """Identify unnatural syntactic or structural parallelism across consecutive paragraphs."""
    signal_id = "signal.structural.repeated_paragraph_structure"
    name = "Repeated Paragraph Structure Uniformity"
    desc = "Identifies unnatural syntactic or structural parallelism across consecutive paragraphs."
    impl_ref = "md_audit.analyzers.structural.detect_repeated_paragraph_structure"
    limitations = "Questionnaire templates, survey specifications, and assignment rubrics intentionally maintain uniform paragraph structure."
    threshold = "Count >= 3 consecutive paragraphs exhibiting structural uniformity or syntactic template matching."

    if len(paragraphs) < 3:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"paragraph_count": len(paragraphs)},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    # Check 1: Bracketed prompt structures (e.g. [Explain ...], [Describe ...])
    bracketed_runs: list[list[ParagraphInfo]] = []
    current_run: list[ParagraphInfo] = []

    for p in paragraphs:
        if p.text.strip().startswith("[") and "]" in p.text:
            current_run.append(p)
        else:
            if len(current_run) >= 3:
                bracketed_runs.append(list(current_run))
            current_run = []
    if len(current_run) >= 3:
        bracketed_runs.append(list(current_run))

    # Check 2: Paragraphs with identical sentence count and nearly identical length
    uniform_len_runs: list[list[ParagraphInfo]] = []
    current_len_run: list[ParagraphInfo] = []

    for p in paragraphs:
        if not p.sufficient_text:
            if len(current_len_run) >= 3:
                uniform_len_runs.append(list(current_len_run))
            current_len_run = []
            continue

        if not current_len_run:
            current_len_run.append(p)
        else:
            prev = current_len_run[-1]
            if prev.sentence_count == p.sentence_count and abs(prev.word_count - p.word_count) <= 4:
                current_len_run.append(p)
            else:
                if len(current_len_run) >= 3:
                    uniform_len_runs.append(list(current_len_run))
                current_len_run = [p]

    if len(current_len_run) >= 3:
        uniform_len_runs.append(list(current_len_run))

    if bracketed_runs or uniform_len_runs:
        supporting: list[str] = []
        loc_paras: list[int] = []
        loc_lines: list[list[int]] = []

        for run in bracketed_runs:
            for p in run:
                supporting.append(f"P{p.index} (L{p.start_line}): bracketed prompt template '{p.text[:60]}...'")
                loc_paras.append(p.index)
                loc_lines.append([p.start_line, p.end_line])

        for run in uniform_len_runs:
            for p in run:
                supporting.append(f"P{p.index} (L{p.start_line}): uniform {p.sentence_count}-sentence structure ({p.word_count} words)")
                loc_paras.append(p.index)
                loc_lines.append([p.start_line, p.end_line])

        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "bracketed_prompt_run_length": max((len(r) for r in bracketed_runs), default=0),
                "uniform_cadence_run_length": max((len(r) for r in uniform_len_runs), default=0),
            },
            threshold=threshold,
            supporting_text=supporting[:8],
            source_location={"paragraphs": sorted(list(set(loc_paras))), "line_ranges": loc_lines[:8]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"bracketed_runs": 0, "uniform_len_runs": 0},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_low_localized_burstiness(windows: list[RollingWindowInfo]) -> StructuralSignal:
    """Detect sustained lack of sentence-length variation over rolling 5-sentence windows."""
    signal_id = "signal.structural.low_localized_burstiness"
    name = "Low Localized Burstiness (Rolling Windows)"
    desc = "Detects sustained lack of sentence-length variation (cadence flatlining) over rolling 5-sentence windows."
    impl_ref = "md_audit.analyzers.structural.detect_low_localized_burstiness"
    limitations = "Summary bullet points, concise technical specifications, and news briefs naturally maintain uniform sentence lengths."
    threshold = "Rolling window CV < 0.25 across at least one 5-sentence window."

    if not windows:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"window_count": 0},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    low_burst_windows = [w for w in windows if w.low_burstiness_detected]
    min_cv = min(w.coefficient_of_variation for w in windows)

    if low_burst_windows:
        supporting = [
            f"Window {w.window_index} (L{w.start_line}-L{w.end_line}): CV={w.coefficient_of_variation:.2f}, mean length={w.mean_length:.1f} words"
            for w in low_burst_windows[:8]
        ]
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "min_window_cv": round(min_cv, 2),
                "low_burstiness_window_count": len(low_burst_windows),
                "total_windows": len(windows),
            },
            threshold=threshold,
            supporting_text=supporting,
            source_location={"line_ranges": [[w.start_line, w.end_line] for w in low_burst_windows[:8]]},
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={
            "min_window_cv": round(min_cv, 2),
            "total_windows": len(windows),
        },
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_generic_claim_clustering(paragraphs: list[ParagraphInfo]) -> StructuralSignal:
    """Detect dense clusters of abstract buzzwords and claims lacking concrete empirical anchors."""
    signal_id = "signal.structural.generic_claim_clustering"
    name = "Generic and Unanchored Claim Clustering"
    desc = "Detects dense clusters of abstract buzzwords and claims lacking concrete empirical anchors (figures, entities, dates)."
    impl_ref = "md_audit.analyzers.structural.detect_generic_claim_clustering"
    limitations = "High-level vision statements, policy summaries, or mission statements legitimately discuss conceptual goals without numbers."
    threshold = "Count >= 3 buzzwords in a single paragraph without concrete numbers, percentages, or citations."

    if not paragraphs:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"paragraph_count": 0},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    flagged_paras: list[tuple[ParagraphInfo, list[str]]] = []

    for p in paragraphs:
        words = [w.lower() for w in re.findall(r"\b[A-Za-z-]+\b", p.text)]
        found_buzzwords = [w for w in words if w in GENERIC_BUZZWORDS]

        # Check for empirical anchoring (numbers, percentages, dates, citations)
        has_anchor = bool(re.search(r"\b\d+(?:\.\d+)?%?\b|\[[0-9]+\]|\([12][0-9]{3}\)", p.text))

        if len(found_buzzwords) >= 3 and not has_anchor:
            flagged_paras.append((p, found_buzzwords))

    if flagged_paras:
        supporting = [
            f"P{p.index} (L{p.start_line}): {len(bw)} buzzwords {list(set(bw))} with no numerical/citation anchors in \"{p.text[:70]}...\""
            for p, bw in flagged_paras[:8]
        ]
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "unanchored_cluster_count": len(flagged_paras),
                "flagged_paragraphs": [p.index for p, _ in flagged_paras],
            },
            threshold=threshold,
            supporting_text=supporting,
            source_location={
                "paragraphs": [p.index for p, _ in flagged_paras],
                "line_ranges": [[p.start_line, p.end_line] for p, _ in flagged_paras[:8]],
            },
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"unanchored_cluster_count": 0},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def detect_semantic_repetition(sentences_with_lines: list[tuple[int, str]]) -> StructuralSignal:
    """Measure lexical and semantic overlap between nearby sentences using non-stopword Jaccard similarity."""
    signal_id = "signal.structural.semantic_repetition"
    name = "Semantic and Lexical Repetition"
    desc = "Measures lexical and semantic token overlap between nearby sentences using non-stopword Jaccard similarity."
    impl_ref = "md_audit.analyzers.structural.detect_semantic_repetition"
    limitations = "Intentional rhetorical parallelism, definitions, or technical explanations repeating key domain terminology."
    threshold = "Jaccard similarity >= 0.55 between nearby sentences (>= 5 content words each)."

    if len(sentences_with_lines) < 4:
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="insufficient_evidence",
            raw_measurement={"sentence_count": len(sentences_with_lines)},
            threshold=threshold,
            supporting_text=[],
            source_location={},
            limitations=limitations,
        )

    # Tokenize content words per sentence
    tokenized: list[tuple[int, str, set[str]]] = []
    for line_no, text in sentences_with_lines:
        words = re.findall(r"\b[A-Za-z0-9_-]+\b", text.lower())
        content_tokens = {w for w in words if w not in STOPWORDS and len(w) > 2}
        if len(content_tokens) >= 5:
            tokenized.append((line_no, text, content_tokens))

    high_overlap_pairs: list[dict[str, Any]] = []
    max_jaccard = 0.0

    n = len(tokenized)
    for i in range(n):
        for j in range(i + 1, min(i + 4, n)):  # Nearby window of 3 sentences
            t1 = tokenized[i][2]
            t2 = tokenized[j][2]
            union = t1 | t2
            if not union:
                continue
            jaccard = len(t1 & t2) / len(union)
            if jaccard > max_jaccard:
                max_jaccard = jaccard

            if jaccard >= 0.55:
                high_overlap_pairs.append({
                    "line_a": tokenized[i][0],
                    "text_a": tokenized[i][1],
                    "line_b": tokenized[j][0],
                    "text_b": tokenized[j][1],
                    "jaccard": round(jaccard, 3),
                    "shared_tokens": sorted(list(t1 & t2)),
                })

    if high_overlap_pairs:
        supporting = [
            f"L{p['line_a']} vs L{p['line_b']} (Jaccard {p['jaccard']}): shared {p['shared_tokens'][:6]}"
            for p in high_overlap_pairs[:6]
        ]
        return StructuralSignal(
            signal_id=signal_id,
            name=name,
            description=desc,
            implementation_reference=impl_ref,
            status="signal_present",
            raw_measurement={
                "max_jaccard_similarity": round(max_jaccard, 3),
                "high_overlap_pair_count": len(high_overlap_pairs),
            },
            threshold=threshold,
            supporting_text=supporting,
            source_location={
                "lines": [[p["line_a"], p["line_b"]] for p in high_overlap_pairs[:6]]
            },
            limitations=limitations,
        )

    return StructuralSignal(
        signal_id=signal_id,
        name=name,
        description=desc,
        implementation_reference=impl_ref,
        status="no_measurable_signal",
        raw_measurement={"max_jaccard_similarity": round(max_jaccard, 3)},
        threshold=threshold,
        supporting_text=[],
        source_location={},
        limitations=limitations,
    )


def analyze_structural_signals(
    doc: ScannedDocument,
    sections: list[SectionInfo],
    paragraphs: list[ParagraphInfo],
    windows: list[RollingWindowInfo],
    sentences_with_lines: list[tuple[int, str]],
) -> list[StructuralSignal]:
    """Execute all 8 structural and formulaic signal detectors."""
    return [
        detect_repeated_paragraph_openings(paragraphs),
        detect_repeated_sentence_openings(sentences_with_lines),
        detect_excessive_transitional_language(doc, sections),
        detect_formulaic_patterns(doc),
        detect_repeated_paragraph_structure(paragraphs),
        detect_low_localized_burstiness(windows),
        detect_generic_claim_clustering(paragraphs),
        detect_semantic_repetition(sentences_with_lines),
    ]
