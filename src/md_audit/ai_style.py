"""AI-style evidence profile generator (Enhancement C).

Produces an independent, transparent, evidence-based assessment of AI-associated
writing characteristics, strictly separated from quality scoring and without
inferring or asserting authorship probabilities.
"""

from __future__ import annotations

from typing import Any, Sequence

from .analyzers.sections import ParagraphInfo, RollingWindowInfo, SectionInfo
from .analyzers.structural import StructuralSignal
from .scanner import ScannedDocument

DISCLAIMER_TEXT = (
    "This assessment evaluates stylistic uniformity, formulaic structures, and rhetorical patterns "
    "commonly associated with generative AI language models. It is an evidence-based stylistic analysis, "
    "NOT a determination of human vs. AI authorship. Human authors can produce formulaic prose, and "
    "AI models can produce natural or varied prose. Zero findings do not prove human authorship."
)


def generate_ai_style_assessment(
    doc: ScannedDocument,
    sections: Sequence[SectionInfo],
    paragraphs: Sequence[ParagraphInfo],
    windows: Sequence[RollingWindowInfo],
    signals: Sequence[StructuralSignal],
) -> dict[str, Any]:
    """
    Synthesize structural and formulaic signals into a standalone ai_style_assessment profile.
    """
    if not signals:
        return {
            "status": "analysis_failed",
            "authorship_determined": False,
            "disclaimer": DISCLAIMER_TEXT,
            "signals": [],
            "highlights": ["Analysis could not be executed: no structural signals available."],
            "limitations": ["No structural signals were provided to the evaluator."],
            "summary": "AI-style assessment could not be performed.",
        }

    present_signals = [s for s in signals if s.status == "signal_present"]
    absent_signals = [s for s in signals if s.status == "no_measurable_signal"]
    insufficient_signals = [s for s in signals if s.status == "insufficient_evidence"]
    not_applicable_signals = [s for s in signals if s.status == "analysis_not_applicable"]

    # Generate highlights from present signals
    highlights: list[str] = []
    for s in present_signals:
        if s.supporting_text:
            first_support = s.supporting_text[0]
            highlights.append(f"{s.name}: {first_support}")
        else:
            highlights.append(f"{s.name} detected meeting threshold ({s.threshold}).")

    if not highlights:
        if insufficient_signals and len(insufficient_signals) >= len(signals) // 2:
            highlights.append("Insufficient document volume for conclusive structural cadence evaluation.")
        else:
            highlights.append("No elevated structural or formulaic AI-associated patterns detected across evaluated signals.")

    # Generate concise, non-authorship summary
    if len(present_signals) >= 4:
        density_label = "elevated"
    elif len(present_signals) >= 1:
        density_label = "moderate"
    else:
        density_label = "minimal"

    summary_parts = [
        f"Document exhibits {density_label} density of AI-associated stylistic patterns ({len(present_signals)} of {len(signals)} signals present)."
    ]
    if present_signals:
        signal_names = [s.name for s in present_signals]
        summary_parts.append(f"Observed signals include: {', '.join(signal_names)}.")
    else:
        summary_parts.append("All evaluatable structural indicators remained within expected human variability ranges.")

    summary_parts.append(
        "Note: Findings reflect formulaic rhetoric and structural cadence, not machine authorship."
    )

    limitations = [
        "Writing style cannot reliably establish document authorship.",
        "Instructional scaffolds, student templates, and formal specifications frequently exhibit structural uniformity without AI origin.",
        "Generative AI models can produce natural, varied, and idiosyncratic prose that does not trigger formulaic signals.",
        "Zero detected signals does not prove human authorship.",
        "Short texts lack sufficient sample size for reliable sentence-length cadence and rolling burstiness evaluation.",
    ]

    return {
        "status": "completed",
        "authorship_determined": False,
        "disclaimer": DISCLAIMER_TEXT,
        "signal_summary": {
            "total_signals_evaluated": len(signals),
            "signals_present": len(present_signals),
            "signals_absent": len(absent_signals),
            "insufficient_evidence": len(insufficient_signals),
            "not_applicable": len(not_applicable_signals),
        },
        "signals": [s.to_dict() for s in signals],
        "highlights": highlights,
        "limitations": limitations,
        "summary": " ".join(summary_parts),
    }
