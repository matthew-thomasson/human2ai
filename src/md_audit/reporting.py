"""Reporting module for terminal, Markdown, and JSON quality audit reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .analyzers.deterministic import Finding
from .analyzers.model_evaluator import ModelEvaluationResult
from .scoring import DirectoryScore, DocumentScore
from .validation import ValidationResult

CATEGORY_DISPLAY_NAMES = {
    "ai_patterns": "AI-style patterns",
    "readability": "Readability",
    "repetition": "Repetition",
    "language_clarity": "Language clarity",
    "consistency": "Consistency",
}


@dataclass
class AuditReport:
    """Complete container for an audit run."""
    directory: str
    timestamp: str
    tool_version: str
    ruleset_version: str
    directory_score: DirectoryScore
    document_scores: list[DocumentScore]
    findings_by_file: dict[str, list[Finding]]
    model_evaluations: list[ModelEvaluationResult] | None = None
    config_summary: dict[str, Any] | None = None


def format_terminal_summary(report: AuditReport) -> str:
    """Format human-readable terminal summary matching brief specifications."""
    lines: list[str] = []
    lines.append("Markdown Quality Audit")
    lines.append("======================")
    lines.append("")
    lines.append(f"Directory: {report.directory}")
    lines.append(f"Files analysed: {report.directory_score.total_files}")
    lines.append("")
    lines.append(f"Overall writing quality: {report.directory_score.overall_score}/100")
    lines.append("")
    lines.append("Category scores:")
    for cat_key, display in CATEGORY_DISPLAY_NAMES.items():
        score = report.directory_score.category_scores.get(cat_key, 100)
        lines.append(f"  {display:<23} {score:>3}/100")

    # Model evaluation summary if present
    if report.model_evaluations:
        lines.append("")
        lines.append("Model-assisted evaluation (independent critic):")
        for m in report.model_evaluations:
            lines.append(f"  {m.file_path}: {m.overall_score}/100 ({m.critique_summary})")

    lines.append("")
    lines.append("Highest-priority findings:")
    lines.append("")

    any_findings = False
    for doc in report.document_scores:
        file_findings = report.findings_by_file.get(doc.file_path, [])
        if not file_findings:
            continue
        any_findings = True
        lines.append(doc.file_path)
        # Deduplicate explanations for summary view
        seen_msgs = set()
        count = 0
        for f in file_findings:
            msg = f.explanation
            if msg not in seen_msgs:
                seen_msgs.add(msg)
                lines.append(f"  - [{f.severity.upper()}] L{f.line_number}: {msg}")
                count += 1
                if count >= 3:
                    break
        remaining = len(file_findings) - count
        if remaining > 0:
            lines.append(f"  - ... and {remaining} more issue(s)")
        lines.append("")

    if not any_findings:
        lines.append("  No critical quality issues detected. Prose is clean and direct.")
        lines.append("")

    imp_count = report.directory_score.files_with_issues
    lines.append(f"Result: {imp_count} file(s) have editorial improvement opportunities.")
    lines.append("")
    lines.append(f"Note: {report.directory_score.disclaimer}")

    return "\n".join(lines)


def format_markdown_report(report: AuditReport) -> str:
    """Generate detailed Markdown report with full diagnostics and scoring breakdown."""
    lines: list[str] = []
    lines.append("# Markdown Quality Audit Report")
    lines.append("")
    lines.append(f"**Directory:** `{report.directory}`  ")
    lines.append(f"**Timestamp:** `{report.timestamp}`  ")
    lines.append(f"**Tool Version:** `md-audit v{report.tool_version}`  ")
    lines.append(f"**Ruleset Version:** `{report.ruleset_version}`  ")
    lines.append("")
    lines.append("> [!NOTE]")
    lines.append(f"> {report.directory_score.disclaimer}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Files analysed:** {report.directory_score.total_files}")
    lines.append(f"- **Total word count:** {report.directory_score.total_words}")
    lines.append(f"- **Overall writing quality:** **{report.directory_score.overall_score}/100**")
    lines.append(f"- **Files with improvement opportunities:** {report.directory_score.files_with_issues}")
    lines.append("")
    lines.append("### Category Scores")
    lines.append("")
    lines.append("| Category | Score | Weight |")
    lines.append("|---|---:|---:|")
    weights = {"ai_patterns": "25%", "readability": "20%", "repetition": "20%", "language_clarity": "20%", "consistency": "15%"}
    for cat_key, display in CATEGORY_DISPLAY_NAMES.items():
        score = report.directory_score.category_scores.get(cat_key, 100)
        lines.append(f"| {display} | {score}/100 | {weights.get(cat_key, '20%')} |")
    lines.append("")

    lines.append("## File-by-File Breakdown")
    lines.append("")
    for doc in report.document_scores:
        lines.append(f"### `{doc.file_path}`")
        lines.append(f"- **Quality Score:** {doc.overall_score}/100")
        lines.append(f"- **Words:** {doc.word_count}")
        lines.append(f"- **Total Findings:** {doc.findings_count}")
        lines.append("")

        file_findings = report.findings_by_file.get(doc.file_path, [])
        if file_findings:
            lines.append("| Line | Severity | Rule ID | Matched Text | Explanation & Suggestion |")
            lines.append("|---:|---|---|---|---|")
            for f in file_findings:
                clean_match = f.matched_text.replace("|", "\\|").replace("\n", " ")
                clean_exp = f.explanation.replace("|", "\\|")
                clean_sug = f.suggested_improvement.replace("|", "\\|")
                lines.append(
                    f"| {f.line_number} | `{f.severity}` | `{f.rule_id}` | `{clean_match}` | {clean_exp} **Suggestion:** {clean_sug} |"
                )
            lines.append("")
        else:
            lines.append("*No issues identified in this file.*")
            lines.append("")

    if report.model_evaluations:
        lines.append("## Model-Assisted Critique (Independent Review)")
        lines.append("")
        for m in report.model_evaluations:
            lines.append(f"### `{m.file_path}`")
            lines.append(f"- **Evaluator Model:** `{m.model_identifier}`")
            lines.append(f"- **Model Quality Score:** {m.overall_score}/100 (Naturalness: {m.naturalness_score}, Clarity: {m.clarity_score}, Coherence: {m.coherence_score})")
            lines.append(f"- **Summary:** {m.critique_summary}")
            if m.weaknesses:
                lines.append("")
                lines.append("| Aspect | Identified Text | Feedback |")
                lines.append("|---|---|---|")
                for w in m.weaknesses:
                    lines.append(f"| {w.aspect} | `{w.quote}` | {w.feedback} |")
            lines.append("")

    return "\n".join(lines)


def format_json_report(report: AuditReport) -> dict[str, Any]:
    """Serialize full report to structured JSON format."""
    return {
        "metadata": {
            "tool": "md-audit",
            "version": report.tool_version,
            "ruleset_version": report.ruleset_version,
            "timestamp": report.timestamp,
            "directory": report.directory,
            "disclaimer": report.directory_score.disclaimer,
        },
        "summary": {
            "files_analyzed": report.directory_score.total_files,
            "total_words": report.directory_score.total_words,
            "overall_writing_quality": report.directory_score.overall_score,
            "category_scores": report.directory_score.category_scores,
            "files_with_issues": report.directory_score.files_with_issues,
            "aggregation_method": report.directory_score.aggregation_method,
        },
        "documents": [
            {
                "file": d.file_path,
                "overall_score": d.overall_score,
                "category_scores": d.category_scores,
                "word_count": d.word_count,
                "findings_count": d.findings_count,
                "rubric_breakdown": d.rubric_breakdown,
                "findings": [
                    f.to_dict() for f in report.findings_by_file.get(d.file_path, [])
                ],
            }
            for d in report.document_scores
        ],
        "model_evaluations": [
            m.to_dict() for m in (report.model_evaluations or [])
        ],
    }


def format_comparison_summary(
    before_report: AuditReport,
    after_report: AuditReport,
    files_changed: int,
    diffs: dict[str, str],
    validation_results: dict[str, ValidationResult],
) -> str:
    """Format before/after comparison table and metrics."""
    lines: list[str] = []
    lines.append("Writing Quality Comparison")
    lines.append("==========================")
    lines.append("")
    lines.append(f"Original directory: {before_report.directory}")
    lines.append(f"Revised directory:  {after_report.directory}")
    lines.append("")

    b_overall = before_report.directory_score.overall_score
    a_overall = after_report.directory_score.overall_score
    diff_overall = a_overall - b_overall
    sign = "+" if diff_overall >= 0 else ""

    lines.append(f"Overall writing quality: {b_overall} -> {a_overall} ({sign}{diff_overall})")
    lines.append("")
    lines.append(f"| {'Metric':<20} | {'Before':>6} | {'After':>6} | {'Change':>6} |")
    lines.append(f"|{'-'*22}|{'-'*8}:|{'-'*8}:|{'-'*8}:|")
    lines.append(f"| {'Writing quality':<20} | {b_overall:>6} | {a_overall:>6} | {sign + str(diff_overall):>6} |")

    for cat_key, display in CATEGORY_DISPLAY_NAMES.items():
        b_cat = before_report.directory_score.category_scores.get(cat_key, 100)
        a_cat = after_report.directory_score.category_scores.get(cat_key, 100)
        d_cat = a_cat - b_cat
        d_sign = "+" if d_cat >= 0 else ""
        lines.append(f"| {display:<20} | {b_cat:>6} | {a_cat:>6} | {d_sign + str(d_cat):>6} |")

    b_findings = sum(len(f) for f in before_report.findings_by_file.values())
    a_findings = sum(len(f) for f in after_report.findings_by_file.values())
    resolved = max(0, b_findings - a_findings)

    lines.append("")
    lines.append(f"Files modified:              {files_changed}")
    lines.append(f"Initial findings count:      {b_findings}")
    lines.append(f"Resolved findings:           {resolved}")
    lines.append(f"Remaining findings:          {a_findings}")
    lines.append("")

    # Semantic preservation validation checks
    lines.append("Semantic Preservation Audit:")
    for f_path, val in validation_results.items():
        if val.is_valid:
            lines.append(f"  [PASSED] {f_path}: All numbers, dates, code blocks, and RFC keywords preserved.")
        else:
            crit_count = sum(1 for c in val.material_changes if c.severity == "critical")
            lines.append(f"  [FLAGGED] {f_path}: {crit_count} potential semantic change(s) detected!")
            for c in val.material_changes:
                lines.append(f"    - {c.change_type} ({c.severity}): {c.explanation}")

    return "\n".join(lines)
