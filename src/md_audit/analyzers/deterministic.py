"""Deterministic rule engine for Markdown writing quality analysis."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
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
    source_file: str = ""


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

    def __init__(
        self,
        rules: Sequence[Rule] | None = None,
        loader_diagnostics: dict[str, Any] | None = None,
    ):
        self.rules: list[Rule] = list(rules) if rules else []
        self.loader_diagnostics: dict[str, Any] = loader_diagnostics or {
            "rules_dir": "",
            "files_scanned": [],
            "rules_loaded_count": len(self.rules),
            "rules_failed_count": 0,
            "rules_loaded": [
                {
                    "id": r.id,
                    "category": r.category,
                    "severity": r.severity,
                    "pattern": r.pattern.pattern,
                    "source_file": r.source_file,
                }
                for r in self.rules
            ],
            "rules_failed": [],
        }
        self.last_diagnostics: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_rules_directory(cls, rules_dir: str | Path) -> DeterministicAnalyzer:
        """Load all YAML rules from a directory with full diagnostics."""
        dir_path = Path(rules_dir).resolve()
        if not dir_path.exists():
            return cls([], loader_diagnostics={
                "rules_dir": str(dir_path),
                "files_scanned": [],
                "rules_loaded_count": 0,
                "rules_failed_count": 0,
                "rules_loaded": [],
                "rules_failed": [],
                "warning": f"Rules directory does not exist: {dir_path}",
            })

        loaded_rules: list[Rule] = []
        files_scanned: list[str] = []
        rules_loaded_info: list[dict[str, Any]] = []
        rules_failed_info: list[dict[str, Any]] = []

        for yaml_file in sorted(dir_path.glob("*.yaml")):
            file_name = yaml_file.name
            files_scanned.append(file_name)
            try:
                raw_text = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(raw_text)
            except Exception as e:
                rules_failed_info.append({
                    "source_file": file_name,
                    "rule_id": None,
                    "error": f"YAML parse error: {e}",
                })
                continue

            if not data or not isinstance(data, dict):
                rules_failed_info.append({
                    "source_file": file_name,
                    "rule_id": None,
                    "error": "File root is not a valid YAML mapping",
                })
                continue

            default_cat = data.get("category", "ai_patterns")
            rule_defs = data.get("rules", [])
            if not isinstance(rule_defs, list):
                rules_failed_info.append({
                    "source_file": file_name,
                    "rule_id": None,
                    "error": "'rules' key is not a list",
                })
                continue

            for r_def in rule_defs:
                if not isinstance(r_def, dict):
                    rules_failed_info.append({
                        "source_file": file_name,
                        "rule_id": None,
                        "error": "Rule entry is not a dictionary",
                    })
                    continue

                r_id = r_def.get("id", "rule.unknown")
                cat = r_def.get("category", default_cat)
                sev = r_def.get("severity", "warning")
                pat_str = r_def.get("pattern", "")
                msg = r_def.get("message", "")
                sug = r_def.get("suggestion", "")

                if not pat_str:
                    rules_failed_info.append({
                        "source_file": file_name,
                        "rule_id": r_id,
                        "error": "Missing or empty 'pattern' definition",
                    })
                    continue

                try:
                    compiled = re.compile(pat_str)
                    rule_obj = Rule(
                        id=r_id,
                        category=cat,
                        severity=sev,
                        pattern=compiled,
                        message=msg,
                        suggestion=sug,
                        source_file=file_name,
                    )
                    loaded_rules.append(rule_obj)
                    rules_loaded_info.append({
                        "id": r_id,
                        "category": cat,
                        "severity": sev,
                        "pattern": pat_str,
                        "source_file": file_name,
                    })
                except re.error as e:
                    rules_failed_info.append({
                        "source_file": file_name,
                        "rule_id": r_id,
                        "pattern": pat_str,
                        "error": f"Invalid regular expression: {e}",
                    })

        loader_diag = {
            "rules_dir": str(dir_path),
            "files_scanned": files_scanned,
            "rules_loaded_count": len(loaded_rules),
            "rules_failed_count": len(rules_failed_info),
            "rules_loaded": rules_loaded_info,
            "rules_failed": rules_failed_info,
        }
        return cls(loaded_rules, loader_diagnostics=loader_diag)

    def analyze(self, doc: ScannedDocument) -> list[Finding]:
        """Analyze a scanned document and return all rule findings with execution diagnostics."""
        t0 = time.perf_counter()
        findings: list[Finding] = []

        non_empty_line_indices = [
            (idx, line) for idx, line in enumerate(doc.prose_lines, start=1) if line.strip()
        ]
        non_empty_count = len(non_empty_line_indices)

        # Track per-rule match evidence
        rule_evaluations: list[dict[str, Any]] = []
        total_line_checks = 0

        if non_empty_count == 0 or doc.word_count == 0:
            status = "not_applicable"
            reason = "Insufficient analysable text (0 prose words)"
            # Initialize empty rule evaluations
            for rule in self.rules:
                rule_evaluations.append({
                    "rule_id": rule.id,
                    "category": rule.category,
                    "severity": rule.severity,
                    "pattern": rule.pattern.pattern,
                    "source_file": rule.source_file,
                    "match_count": 0,
                    "matches": [],
                })
        else:
            status = "executed"
            reason = None

            for rule in self.rules:
                rule_matches = []
                for line_idx, line in non_empty_line_indices:
                    total_line_checks += 1
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
                        rule_matches.append({
                            "line": line_idx,
                            "column": col,
                            "matched_text": matched_str,
                        })

                rule_evaluations.append({
                    "rule_id": rule.id,
                    "category": rule.category,
                    "severity": rule.severity,
                    "pattern": rule.pattern.pattern,
                    "source_file": rule.source_file,
                    "match_count": len(rule_matches),
                    "matches": rule_matches,
                })

        # Multi-line checks
        openings_findings = self._check_repeated_openings(doc) if status == "executed" else []
        findings.extend(openings_findings)

        terms_findings = self._check_inconsistent_terms(doc) if status == "executed" else []
        findings.extend(terms_findings)

        # Sort findings by line and column
        findings.sort(key=lambda f: (f.line_number, f.column))

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        checks_performed = total_line_checks + len(INCONSISTENT_TERM_PAIRS) + 1
        checks_triggered = len(findings)

        self.last_diagnostics[doc.path] = {
            "component": "yaml_rule_analyzer",
            "implementation": "md_audit.analyzers.deterministic.DeterministicAnalyzer",
            "version": "1.0.0",
            "status": status,
            "reason": reason,
            "input_size": {
                "raw_characters": doc.char_count,
                "raw_lines": len(doc.raw_lines),
                "prose_lines": len(doc.prose_lines),
                "prose_words": doc.word_count,
                "non_empty_prose_lines": non_empty_count,
            },
            "rules_count_total": len(self.rules),
            "rules_evaluated_count": len(self.rules) if status == "executed" else 0,
            "rules_triggered_count": sum(1 for r in rule_evaluations if r["match_count"] > 0),
            "rules_evaluated": rule_evaluations,
            "multi_line_checks": {
                "repeated_sentence_openings": {
                    "evaluated": status == "executed",
                    "findings_count": len(openings_findings),
                },
                "terminology_consistency": {
                    "evaluated": status == "executed",
                    "pairs_checked": len(INCONSISTENT_TERM_PAIRS),
                    "findings_count": len(terms_findings),
                },
            },
            "checks_performed": checks_performed,
            "checks_triggered": checks_triggered,
            "findings_count": len(findings),
            "findings": [f.to_dict() for f in findings],
            "duration_ms": elapsed_ms,
            "errors": [],
            "warnings": [],
        }

        return findings

    def get_document_diagnostics(self, doc_path: str) -> dict[str, Any]:
        """Retrieve execution diagnostics for a specific analyzed document."""
        return self.last_diagnostics.get(doc_path, {})

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
