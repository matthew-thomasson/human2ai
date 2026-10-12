"""Semantic preservation gate and protected elements validator."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

RFC_2119_KEYWORDS = {
    "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
    "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED",
    "MAY", "OPTIONAL",
}


@dataclass
class MaterialChange:
    """Represents a potentially breaking semantic change detected between original and revised text."""
    change_type: str  # numerical_value, date_or_deadline, technical_requirement, code_block, inline_identifier, url_or_link, markdown_structure
    severity: str     # critical, warning
    original_value: str
    revised_value: str
    explanation: str

    def to_dict(self) -> dict:
        return {
            "type": self.change_type,
            "severity": self.severity,
            "original": self.original_value,
            "revised": self.revised_value,
            "explanation": self.explanation,
        }


@dataclass
class ValidationResult:
    """Outcome of comparing original vs revised text for semantic preservation."""
    is_valid: bool
    material_changes: list[MaterialChange]
    preserved_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "critical_changes_count": sum(1 for c in self.material_changes if c.severity == "critical"),
            "warning_changes_count": sum(1 for c in self.material_changes if c.severity == "warning"),
            "material_changes": [c.to_dict() for c in self.material_changes],
            "preserved_counts": self.preserved_counts,
        }


def extract_numbers(text: str) -> Counter[str]:
    """
    Extract numerical tokens including integers, floats, percentages,
    ports, versions, and units (e.g. 99.9%, v2.1.0, 8080, 500ms).
    """
    # Matches numbers with optional decimals, percentages, or units
    pattern = r"(?<![A-Za-z_])(?:\bv?\d+(?:\.\d+)+(?:-[a-z0-9]+)?|\b\d+(?:\.\d+)?%?|\b\d+(?:ms|s|m|h|kb|mb|gb|tb|px|rem|em|hz|khz|mhz|ghz)\b)"
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    # Normalize to lowercase
    return Counter(m.lower() for m in matches)


def extract_dates(text: str) -> Counter[str]:
    """Extract dates such as YYYY-MM-DD, Month DD YYYY, or Q1 2026."""
    pattern = (
        r"\b(?:\d{4}-\d{2}-\d{2}"
        r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
        r"|Q[1-4]\s+\d{4}"
        r"|\d{4}-Q[1-4])\b"
    )
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    return Counter(m.lower() for m in matches)


def extract_rfc_keywords(text: str) -> Counter[str]:
    """Extract uppercase RFC-2119 requirement keywords."""
    found: list[str] = []
    # Check multi-word keywords first
    for multi in ["MUST NOT", "SHALL NOT", "NOT RECOMMENDED", "SHOULD NOT"]:
        for _ in re.finditer(rf"\b{multi}\b", text):
            found.append(multi)
    # Check single-word keywords
    for single in ["MUST", "REQUIRED", "SHALL", "SHOULD", "RECOMMENDED", "MAY", "OPTIONAL"]:
        # Only match uppercase to avoid colloquial "may" or "should"
        for _ in re.finditer(rf"\b{single}\b", text):
            found.append(single)
    return Counter(found)


def extract_fenced_code_blocks(text: str) -> list[str]:
    """Extract full content of fenced code blocks verbatim."""
    pattern = r"```(?:[a-zA-Z0-9_-]+)?\n(.*?)```"
    return re.findall(pattern, text, flags=re.DOTALL)


def extract_inline_code(text: str) -> Counter[str]:
    """Extract inline backticked identifiers."""
    matches = re.findall(r"`([^`\n]+)`", text)
    return Counter(m.strip() for m in matches if m.strip())


def extract_urls(text: str) -> Counter[str]:
    """Extract URLs from markdown links, image links, or autolinks."""
    pattern = r"(?:\[.*?\]\((https?://[^)]+)\)|<(https?://[^>]+)>|\b(https?://[^\s)\]]+))"
    matches = re.findall(pattern, text)
    urls = []
    for m in matches:
        url = m[0] or m[1] or m[2]
        if url:
            urls.append(url.strip())
    return Counter(urls)


def extract_headings(text: str) -> list[tuple[int, str]]:
    """Extract markdown headings with level and title."""
    headings = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            headings.append((len(m.group(1)), m.group(2).strip()))
    return headings


class SemanticPreservationGate:
    """Verifies that editorial rewriting preserves all protected facts and technical structures."""

    def __init__(
        self,
        strict_numbers: bool = True,
        strict_dates: bool = True,
        strict_requirements: bool = True,
        strict_code: bool = True,
        strict_urls: bool = True,
        strict_structure: bool = True,
    ):
        self.strict_numbers = strict_numbers
        self.strict_dates = strict_dates
        self.strict_requirements = strict_requirements
        self.strict_code = strict_code
        self.strict_urls = strict_urls
        self.strict_structure = strict_structure

    def validate(self, original_text: str, revised_text: str) -> ValidationResult:
        """
        Compare original and revised text. Returns ValidationResult indicating whether
        the edit is safe to accept, or if material changes require rejection.
        """
        changes: list[MaterialChange] = []
        preserved_counts: dict[str, int] = {}

        # 1. Check Fenced Code Blocks (must be byte-for-byte identical)
        orig_code = extract_fenced_code_blocks(original_text)
        rev_code = extract_fenced_code_blocks(revised_text)
        preserved_counts["code_blocks"] = len(orig_code)

        if self.strict_code:
            if len(orig_code) != len(rev_code):
                changes.append(
                    MaterialChange(
                        change_type="code_block",
                        severity="critical",
                        original_value=f"{len(orig_code)} code block(s)",
                        revised_value=f"{len(rev_code)} code block(s)",
                        explanation="Number of fenced code blocks was altered during rewriting.",
                    )
                )
            else:
                for idx, (c1, c2) in enumerate(zip(orig_code, rev_code)):
                    if c1 != c2:
                        changes.append(
                            MaterialChange(
                                change_type="code_block",
                                severity="critical",
                                original_value=c1[:60] + "...",
                                revised_value=c2[:60] + "...",
                                explanation=f"Code content in block #{idx+1} was modified during rewriting.",
                            )
                        )

        # 2. Check Numerical Values
        orig_nums = extract_numbers(original_text)
        rev_nums = extract_numbers(revised_text)
        preserved_counts["numbers"] = sum(orig_nums.values())

        if self.strict_numbers:
            # Check for missing original numbers
            for num, count in orig_nums.items():
                rev_count = rev_nums.get(num, 0)
                if rev_count < count:
                    changes.append(
                        MaterialChange(
                            change_type="numerical_value",
                            severity="critical",
                            original_value=f"'{num}' ({count}x)",
                            revised_value=f"'{num}' ({rev_count}x)",
                            explanation=f"Numerical value '{num}' is missing or reduced in frequency in the revised text.",
                        )
                    )
            # Check for invented numbers
            for num, count in rev_nums.items():
                orig_count = orig_nums.get(num, 0)
                if orig_count == 0:
                    changes.append(
                        MaterialChange(
                            change_type="numerical_value",
                            severity="critical",
                            original_value="(absent)",
                            revised_value=f"'{num}'",
                            explanation=f"New numerical value '{num}' was introduced into the revised text.",
                        )
                    )

        # 3. Check Dates and Deadlines
        orig_dates = extract_dates(original_text)
        rev_dates = extract_dates(revised_text)
        preserved_counts["dates"] = sum(orig_dates.values())

        if self.strict_dates:
            for date_str, count in orig_dates.items():
                rev_count = rev_dates.get(date_str, 0)
                if rev_count < count:
                    changes.append(
                        MaterialChange(
                            change_type="date_or_deadline",
                            severity="critical",
                            original_value=date_str,
                            revised_value="(missing)",
                            explanation=f"Date or deadline '{date_str}' was altered or omitted.",
                        )
                    )

        # 4. Check Technical Requirement Keywords (RFC 2119)
        orig_rfc = extract_rfc_keywords(original_text)
        rev_rfc = extract_rfc_keywords(revised_text)
        preserved_counts["rfc_keywords"] = sum(orig_rfc.values())

        if self.strict_requirements:
            for kw, count in orig_rfc.items():
                rev_count = rev_rfc.get(kw, 0)
                if rev_count < count:
                    changes.append(
                        MaterialChange(
                            change_type="technical_requirement",
                            severity="critical",
                            original_value=f"{kw} ({count}x)",
                            revised_value=f"{kw} ({rev_count}x)",
                            explanation=f"RFC requirement keyword '{kw}' was altered, weakened, or removed.",
                        )
                    )

        # 5. Check URLs and Link Targets
        orig_urls = extract_urls(original_text)
        rev_urls = extract_urls(revised_text)
        preserved_counts["urls"] = sum(orig_urls.values())

        if self.strict_urls:
            for url, count in orig_urls.items():
                if rev_urls.get(url, 0) < count:
                    changes.append(
                        MaterialChange(
                            change_type="url_or_link",
                            severity="critical",
                            original_value=url,
                            revised_value="(missing)",
                            explanation=f"Target URL '{url}' was removed or modified.",
                        )
                    )

        # 6. Check Inline Code Identifiers
        orig_inline = extract_inline_code(original_text)
        rev_inline = extract_inline_code(revised_text)
        preserved_counts["inline_identifiers"] = sum(orig_inline.values())

        for ident, count in orig_inline.items():
            if rev_inline.get(ident, 0) < count:
                changes.append(
                    MaterialChange(
                        change_type="inline_identifier",
                        severity="warning",
                        original_value=f"`{ident}`",
                        revised_value="(missing)",
                        explanation=f"Inline technical identifier `{ident}` was modified or removed.",
                    )
                )

        # 7. Check Heading Structure
        orig_headings = extract_headings(original_text)
        rev_headings = extract_headings(revised_text)
        preserved_counts["headings"] = len(orig_headings)

        if self.strict_structure:
            if len(orig_headings) != len(rev_headings):
                changes.append(
                    MaterialChange(
                        change_type="markdown_structure",
                        severity="warning",
                        original_value=f"{len(orig_headings)} headings",
                        revised_value=f"{len(rev_headings)} headings",
                        explanation="The number of Markdown headings differs between original and revised text.",
                    )
                )

        has_critical = any(c.severity == "critical" for c in changes)
        is_valid = not has_critical

        return ValidationResult(
            is_valid=is_valid,
            material_changes=changes,
            preserved_counts=preserved_counts,
        )
