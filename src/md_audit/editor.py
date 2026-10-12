"""Editorial rewriting engine with targeted improvements and safety validation."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .scanner import ScannedDocument
from .analyzers.deterministic import Finding
from .validation import SemanticPreservationGate, ValidationResult

# Direct, precision substitution rules for editorial improvement
EDITORIAL_REPLACEMENTS = [
    # Wordiness
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bhas the ability to\b", re.I), "can"),
    (re.compile(r"\bhave the ability to\b", re.I), "can"),
    (re.compile(r"\bis indicative of\b", re.I), "indicates"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\bfor the purpose of\b", re.I), "to"),
    (re.compile(r"\bin the event that\b", re.I), "if"),
    (re.compile(r"\bserves as\b", re.I), "is"),
    # AI clichés & hyperbole
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
    (re.compile(r"\bleverage\b", re.I), "use"),
    (re.compile(r"\bleveraging\b", re.I), "using"),
    (re.compile(r"\bleveraged\b", re.I), "used"),
    (re.compile(r"\butilize\b", re.I), "use"),
    (re.compile(r"\butilizing\b", re.I), "using"),
    (re.compile(r"\butilized\b", re.I), "used"),
    # Formulaic openers & closers
    (re.compile(r"^\s*In today's fast-paced (?:world|digital landscape),\s*", re.I | re.M), ""),
    (re.compile(r"^\s*In the digital age,\s*", re.I | re.M), ""),
    (re.compile(r"^\s*Now more than ever,\s*", re.I | re.M), ""),
    (re.compile(r"^\s*In conclusion,\s*", re.I | re.M), ""),
    (re.compile(r"^\s*In summary,\s*", re.I | re.M), ""),
    (re.compile(r"^\s*All in all,\s*", re.I | re.M), ""),
    (re.compile(r"\bIt is worth noting that\b", re.I), "Note that"),
    (re.compile(r"\bIt's important to note that\b", re.I), "Note that"),
    # Repetitive transitions
    (re.compile(r"^\s*Moreover,\s*", re.I | re.M), ""),
    (re.compile(r"^\s*Furthermore,\s*", re.I | re.M), ""),
    # Generic adjectives
    (re.compile(r"\bgroundbreaking\b", re.I), "novel"),
    (re.compile(r"\bmultifaceted\b", re.I), "complex"),
]


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


class EditorialEngine:
    """Proposes and applies targeted editorial improvements while strictly preserving protected content."""

    def __init__(self, validator: SemanticPreservationGate | None = None):
        self.validator = validator or SemanticPreservationGate()

    def improve_document(
        self,
        doc: ScannedDocument,
        findings: Sequence[Finding] | None = None,
    ) -> EditorialResult:
        """Apply targeted editorial improvements while preserving code, tables, and protected facts."""
        original = doc.raw_content

        # 1. Isolate fenced code blocks to prevent any accidental modification
        code_blocks: list[str] = []
        def save_code_block(match: re.Match) -> str:
            token = f"⟦FENCED_CODE_BLOCK_{len(code_blocks)}⟧"
            code_blocks.append(match.group(0))
            return token

        isolated = re.sub(r"```[a-zA-Z0-9_-]*\n.*?```", save_code_block, original, flags=re.DOTALL)

        # 2. Isolate inline code
        inline_codes: list[str] = []
        def save_inline_code(match: re.Match) -> str:
            token = f"⟦INLINE_CODE_{len(inline_codes)}⟧"
            inline_codes.append(match.group(0))
            return token

        isolated = re.sub(r"`[^`\n]+`", save_inline_code, isolated)

        # 3. Isolate Markdown link URLs
        link_urls: list[str] = []
        def save_link_url(match: re.Match) -> str:
            anchor = match.group(1)
            url = match.group(2)
            token = f"⟦LINK_URL_{len(link_urls)}⟧"
            link_urls.append(url)
            return f"[{anchor}]({token})"

        isolated = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", save_link_url, isolated)

        # 4. Apply targeted replacements on the protected prose
        revised_text = isolated
        changes_count = 0

        # Negative parallelism fix: "It's not just X, it's Y" -> "It is Y"
        neg_par_pattern = re.compile(
            r"\b(?:It'?s|This is)\s+not\s+(?:just\s+)?[^,.;]+,\s*(?:it'?s|it is)\s+",
            re.IGNORECASE,
        )
        if neg_par_pattern.search(revised_text):
            revised_text = neg_par_pattern.sub("It is ", revised_text)
            changes_count += 1

        for pattern, replacement in EDITORIAL_REPLACEMENTS:
            if pattern.search(revised_text):
                revised_text = pattern.sub(replacement, revised_text)
                changes_count += 1

        # 5. Clean up any leftover double spaces in prose before restoring code blocks
        revised_text = re.sub(r"[ \t]+", " ", revised_text)

        # Restore isolated tokens verbatim
        for idx, url in enumerate(link_urls):
            revised_text = revised_text.replace(f"⟦LINK_URL_{idx}⟧", url)

        for idx, code in enumerate(inline_codes):
            revised_text = revised_text.replace(f"⟦INLINE_CODE_{idx}⟧", code)

        for idx, block in enumerate(code_blocks):
            revised_text = revised_text.replace(f"⟦FENCED_CODE_BLOCK_{idx}⟧", block)

        # Preserve markdown line breaks without trailing spaces on prose lines
        revised_text = "\n".join(line.rstrip() for line in revised_text.splitlines())

        # 6. Validate the revised text against original using the Semantic Preservation Gate
        validation_res = self.validator.validate(original, revised_text)

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                revised_text.splitlines(keepends=True),
                fromfile=f"a/{doc.path}",
                tofile=f"b/{doc.path}",
            )
        )
        diff_str = "".join(diff_lines)

        return EditorialResult(
            file_path=doc.path,
            original_content=original,
            revised_content=revised_text if validation_res.is_valid else original,
            diff=diff_str,
            validation=validation_res,
            changes_count=changes_count if validation_res.is_valid else 0,
            is_safe=validation_res.is_valid,
        )
