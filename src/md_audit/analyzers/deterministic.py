"""Deterministic rule engine for Markdown writing quality analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import yaml

from ..scanner import ScannedDocument


@dataclass
class Finding:
    """Represents an editorial or writing quality issue detected in a document."""
    file_path: str
    line_number: int  # 1-indexed
    column: int  # 1-indexed
    rule_id: str
    category: str  # ai_patterns, readability, repetition, language_clarity, consistency
    severity: str  # error, warning, suggestion
    matched_text: str
    explanation: str
    suggested_improvement: str

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line": self.line_number,
            "column": self.column,
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "matched_text": self.matched_text,
            "explanation": self.explanation,
            "suggestion": self.suggested_improvement,
        }


@dataclass
class Rule:
    """Single declarative rule loaded from YAML."""
    id: str
    category: str
    severity: str
    pattern: re.Pattern
    message: str
    suggestion: str


# Common terminology pairs where mixing variants signals inconsistency
INCONSISTENT_TERM_PAIRS = [
    (re.compile(r"\bfront-end\b", re.I), re.compile(r"\bfrontend\b", re.I), "front-end", "frontend"),
    (re.compile(r"\bback-end\b", re.I), re.compile(r"\bbackend\b", re.I), "back-end", "backend"),
    (re.compile(r"\be-mail\b", re.I), re.compile(r"\bemail\b", re.I), "e-mail", "email"),
    (re.compile(r"\bon-premise\b", re.I), re.compile(r"\bon-premises\b", re.I), "on-premise", "on-premises"),
    (re.compile(r"\bdataset\b", re.I), re.compile(r"\bdata set\b", re.I), "dataset", "data set"),
    (re.compile(r"\bplugin\b", re.I), re.compile(r"\bplug-in\b", re.I), "plugin", "plug-in"),
]


class DeterministicAnalyzer:
    """Evaluates Markdown prose against declarative style and AI-pattern rules."""

    def __init__(self, rules: Sequence[Rule] | None = None):
        self.rules: list[Rule] = list(rules) if rules else []

    @classmethod
    def from_rules_directory(cls, rules_dir: str | Path) -> DeterministicAnalyzer:
        """Load all YAML rules from a directory."""
        dir_path = Path(rules_dir).resolve()
        if not dir_path.exists():
            return cls([])

        loaded_rules: list[Rule] = []
        for yaml_file in dir_path.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not data or not isinstance(data, dict):
                    continue
                default_cat = data.get("category", "ai_patterns")
                for r_def in data.get("rules", []):
                    r_id = r_def.get("id", "rule.unknown")
                    cat = r_def.get("category", default_cat)
                    sev = r_def.get("severity", "warning")
                    pat_str = r_def.get("pattern", "")
                    msg = r_def.get("message", "")
                    sug = r_def.get("suggestion", "")

                    if pat_str:
                        compiled = re.compile(pat_str)
                        loaded_rules.append(
                            Rule(
                                id=r_id,
                                category=cat,
                                severity=sev,
                                pattern=compiled,
                                message=msg,
                                suggestion=sug,
                            )
                        )
            except Exception as e:
                # Log or handle rule load error
                continue

        return cls(loaded_rules)

    def analyze(self, doc: ScannedDocument) -> list[Finding]:
        """Analyze a scanned document and return all rule findings."""
        findings: list[Finding] = []

        # 1. Line-by-line regex rule checks
        for line_idx, line in enumerate(doc.prose_lines, start=1):
            if not line.strip():
                continue

            for rule in self.rules:
                for match in rule.pattern.finditer(line):
                    col = match.start() + 1
                    matched_str = match.group(0).strip()
                    findings.append(
                        Finding(
                            file_path=doc.path,
                            line_number=line_idx,
                            column=col,
                            rule_id=rule.id,
                            category=rule.category,
                            severity=rule.severity,
                            matched_text=matched_str,
                            explanation=rule.message,
                            suggested_improvement=rule.suggestion,
                        )
                    )

        # 2. Multi-line analysis: Repeated sentence openings
        findings.extend(self._check_repeated_openings(doc))

        # 3. Terminology consistency check
        findings.extend(self._check_inconsistent_terms(doc))

        # Sort findings by line and column
        findings.sort(key=lambda f: (f.line_number, f.column))
        return findings

    def _check_repeated_openings(self, doc: ScannedDocument) -> list[Finding]:
        """Detect sequences of 3+ consecutive sentences starting with the same word."""
        findings: list[Finding] = []
        sentence_entries: list[tuple[int, str]] = []  # (line_number, first_word)

        for line_idx, line in enumerate(doc.prose_lines, start=1):
            stripped = line.strip()
            # Ignore headers, list bullets, or empty lines for this check
            if not stripped or stripped.startswith(("#", "-", "*", ">", "|", "1.", "2.", "3.")):
                continue

            # Split into sentence-like segments
            raw_sentences = re.split(r"(?<=[.!?])\s+", stripped)
            for s in raw_sentences:
                words = re.findall(r"\b[A-Za-z]+\b", s)
                if words:
                    first_word = words[0].lower()
                    sentence_entries.append((line_idx, first_word))

        if len(sentence_entries) >= 3:
            for i in range(len(sentence_entries) - 2):
                w1 = sentence_entries[i][1]
                w2 = sentence_entries[i + 1][1]
                w3 = sentence_entries[i + 2][1]
                if w1 == w2 == w3 and len(w1) > 2:
                    line_num = sentence_entries[i + 2][0]
                    findings.append(
                        Finding(
                            file_path=doc.path,
                            line_number=line_num,
                            column=1,
                            rule_id="repetition.sentence_openers",
                            category="repetition",
                            severity="warning",
                            matched_text=f"'{w1.capitalize()}' repeated 3 times",
                            explanation=f"Three consecutive sentences begin with the same word ('{w1}').",
                            suggested_improvement="Vary your sentence openings to create natural prose cadence.",
                        )
                    )

        return findings

    def _check_inconsistent_terms(self, doc: ScannedDocument) -> list[Finding]:
        """Check for contradictory or mixed spellings of the same technical term."""
        findings: list[Finding] = []
        full_text = doc.prose_content

        for pat_a, pat_b, term_a, term_b in INCONSISTENT_TERM_PAIRS:
            match_a = pat_a.search(full_text)
            match_b = pat_b.search(full_text)
            if match_a and match_b:
                # Find line number of second occurrence
                line_b = 1
                for idx, line in enumerate(doc.prose_lines, start=1):
                    if pat_b.search(line):
                        line_b = idx
                        break

                findings.append(
                    Finding(
                        file_path=doc.path,
                        line_number=line_b,
                        column=1,
                        rule_id="consistency.terminology",
                        category="consistency",
                        severity="warning",
                        matched_text=f"'{term_a}' vs '{term_b}'",
                        explanation=f"Document mixes inconsistent variants '{term_a}' and '{term_b}'.",
                        suggested_improvement=f"Standardize on one form throughout the document (recommended: '{term_a}').",
                    )
                )

        return findings
