"""Editorial rewriting engine with targeted improvements, LLM rewriter, and safety validation."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .analyzers.deterministic import Finding
from .llm import (
    LLMEditor,
    LLMReviewer,
    ModelError,
    ReviewResult,
    isolate_markdown_elements,
    restore_markdown_elements,
)
from .scanner import ScannedDocument
from .validation import SemanticPreservationGate, ValidationResult

# Direct, safe precision substitution rules for deterministic editorial improvement.
# Simple, verified replacements that do not remove clauses or change meaning.
SAFE_EDITORIAL_REPLACEMENTS = [
    # Wordiness (casing preserved dynamically)
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bhas the ability to\b", re.I), "can"),
    (re.compile(r"\bhave the ability to\b", re.I), "can"),
    (re.compile(r"\bis indicative of\b", re.I), "indicates"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\bfor the purpose of\b", re.I), "to"),
    (re.compile(r"\bin the event that\b", re.I), "if"),
    (re.compile(r"\bserves as\b", re.I), "is"),
    # Clichés & empty corporate puffery
    (re.compile(r"\bstands? as a testament to\b", re.I), "demonstrates"),
    (re.compile(r"\bdelve into\b", re.I), "examine"),
    (re.compile(r"\bdelves into\b", re.I), "examines"),
    (re.compile(r"\bdelved into\b", re.I), "examined"),
    (re.compile(r"\bplays a pivotal role in\b", re.I), "is central to"),
    (re.compile(r"\bplays a crucial role in\b", re.I), "is essential to"),
    (re.compile(r"\brich tapestry of\b", re.I), "range of"),
    (re.compile(r"\btapestry of\b", re.I), "range of"),
    (re.compile(r"\bunlock the full potential of\b", re.I), "maximize"),
    (re.compile(r"\bunlock potential\b", re.I), "improve capability"),
    (re.compile(r"\bfoster seamless collaboration\b", re.I), "help teams collaborate"),
    (re.compile(r"\bfosters collaboration\b", re.I), "helps teams collaborate"),
    (re.compile(r"\bgame-changer\b", re.I), "significant advancement"),
    (re.compile(r"\bharness the power of\b", re.I), "use"),
    (re.compile(r"\bleverages?\b", re.I), "use"),
    (re.compile(r"\bleveraging\b", re.I), "using"),
    (re.compile(r"\bleveraged\b", re.I), "used"),
    (re.compile(r"\butilizes?\b", re.I), "use"),
    (re.compile(r"\butilizing\b", re.I), "using"),
    (re.compile(r"\butilized\b", re.I), "used"),
    (re.compile(r"\bgroundbreaking\b", re.I), "novel"),
    (re.compile(r"\bmultifaceted\b", re.I), "complex"),
    (re.compile(r"\bIt is worth noting that\b", re.I), "Note that"),
    (re.compile(r"\bIt's important to note that\b", re.I), "Note that"),
]


def strip_leading_openers(text: str) -> tuple[str, int]:
    """
    Safely strip formulaic openers at the beginning of lines/paragraphs
    while preserving indentation and capitalizing the following word so
    sentences never start with lowercase letters.
    """
    opener_pattern = re.compile(
        r"(?m)^([ \t]*)(?:In today's fast-paced (?:world|digital landscape)|"
        r"In the digital age|Now more than ever|In conclusion|In summary|All in all|"
        r"Moreover|Furthermore),\s*([a-zA-Z])"
    )
    changes = 0

    def repl(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        indent = m.group(1)
        next_char = m.group(2).upper()
        return f"{indent}{next_char}"

    revised = opener_pattern.sub(repl, text)
    return revised, changes


def apply_safe_replacements(text: str) -> tuple[str, int]:
    """
    Apply word and phrase replacements with dynamic casing preservation
    (e.g., 'In order to' -> 'To', 'in order to' -> 'to').
    """
    changes = 0
    revised = text

    for pat, base_replacement in SAFE_EDITORIAL_REPLACEMENTS:
        def match_handler(m: re.Match) -> str:
            nonlocal changes
            changes += 1
            orig = m.group(0)
            if orig and orig[0].isupper() and base_replacement:
                return base_replacement[0].upper() + base_replacement[1:]
            return base_replacement

        if pat.search(revised):
            revised = pat.sub(match_handler, revised)

    return revised, changes


@dataclass
class EditorialResult:
    """Outcome of editorial improvement for a single file."""
    file_path: str
    original_content: str
    revised_content: str
    diff: str
    validation: ValidationResult
    changes_count: int
    is_safe: bool
    mode: str = "deterministic"
    review: ReviewResult | None = None
    proposed_content: str = ""
    has_proposed_changes: bool = False


class EditorialEngine:
    """Proposes and applies targeted editorial improvements while strictly preserving protected content."""

    def __init__(
        self,
        validator: SemanticPreservationGate | None = None,
        llm_editor: LLMEditor | None = None,
        llm_reviewer: LLMReviewer | None = None,
    ):
        self.validator = validator or SemanticPreservationGate()
        self.llm_editor = llm_editor
        self.llm_reviewer = llm_reviewer

    def improve_document(
        self,
        doc: ScannedDocument,
        findings: Sequence[Finding] | None = None,
        use_llm: bool = False,
        mode: str = "balanced",
        run_review: bool = False,
    ) -> EditorialResult:
        """
        Apply editorial improvements.
        If use_llm is True, invokes LLM contextual editor with mode ('conservative' | 'balanced').
        Otherwise, applies deterministic safe substitutions.
        If run_review is True, runs the independent reviewer.
        Always validates output through SemanticPreservationGate.
        """
        original = doc.raw_content
        changes_count = 0
        review_result: ReviewResult | None = None

        if use_llm and self.llm_editor:
            # 1. LLM Contextual Rewriting
            revised_text = self.llm_editor.rewrite(original, mode=mode)
            changes_count = 1 if revised_text.strip() != original.strip() else 0
        else:
            # 2. Deterministic safe substitutions
            # Step A: Isolate code blocks, inline code, and links
            isolated, code_blocks, inline_codes, link_urls = isolate_markdown_elements(original)

            # Step B: Safe opener stripping with capitalization fix
            revised_text, opener_changes = strip_leading_openers(isolated)
            changes_count += opener_changes

            # Step C: Precision substitutions with case preservation
            revised_text, repl_changes = apply_safe_replacements(revised_text)
            changes_count += repl_changes

            # Step D: Clean leftover double spaces in prose
            revised_text = re.sub(r"[ \t]+", " ", revised_text)

            # Step E: Restore isolated tokens verbatim
            revised_text = restore_markdown_elements(revised_text, code_blocks, inline_codes, link_urls)

        # Preserve markdown line breaks without trailing spaces
        revised_text = "\n".join(line.rstrip() for line in revised_text.splitlines())

        proposed_text = revised_text
        has_proposed_changes = (proposed_text.strip() != original.strip())

        # 3. Deterministic Semantic Preservation Validation
        validation_res = self.validator.validate(original, proposed_text)

        # 4. Optional Independent LLM Review
        # Run review only if changes were proposed and deterministic validation passed
        if run_review and self.llm_reviewer and validation_res.is_valid and has_proposed_changes:
            review_result = self.llm_reviewer.review(original, proposed_text)

        # A revision is accepted ONLY IF:
        # - changes were proposed
        # - deterministic preservation gate passed
        # - if review was requested, reviewer explicitly decided "Accept"
        is_accepted = (
            has_proposed_changes
            and validation_res.is_valid
            and (not run_review or (review_result is not None and review_result.decision == "Accept"))
        )

        if is_accepted:
            final_content = proposed_text
            final_changes = changes_count
        else:
            # Retain original document if rejected, manual review recommended, unreviewed, or safety gate failed
            final_content = original
            final_changes = 0

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                final_content.splitlines(keepends=True),
                fromfile=f"a/{doc.path}",
                tofile=f"b/{doc.path}",
            )
        )
        diff_str = "".join(diff_lines)

        is_safe = validation_res.is_valid and (review_result is None or review_result.decision == "Accept")

        return EditorialResult(
            file_path=doc.path,
            original_content=original,
            revised_content=final_content,
            diff=diff_str,
            validation=validation_res,
            changes_count=final_changes,
            is_safe=is_safe,
            mode=mode if use_llm else "deterministic",
            review=review_result,
            proposed_content=proposed_text,
            has_proposed_changes=has_proposed_changes,
        )
