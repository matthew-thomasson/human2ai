"""Dataset metadata and provenance validation (M2.1 and M3).

Enforces strict provenance integrity, SHA-256 content verification,
and schema validation to prevent misrepresenting synthetic or uncertain
samples as independently verified human-authored documents.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

VALID_PROVENANCE_STATUSES = {
    "verified",          # Independently verified provenance with traceable authentic source
    "documented",        # Documented provenance with credible attribution but secondary source
    "synthetic",         # Deliberately created synthetic or simulated text (e.g., student simulation)
    "uncertain",         # Provenance unclear, disputed, or unverifiable
}

VALID_ORIGIN_LABELS = {
    "human_authored",    # Authored entirely by human(s)
    "ai_generated",      # Authored entirely by AI model(s)
    "ai_edited",         # Human draft subsequently copyedited or transformed by AI
    "mixed_origin",      # Sections of human prose combined with sections of AI prose
    "synthetic_simulation", # Synthetic prose simulating a human or AI style
}

VALID_SPLITS = {
    "development",       # Used for exploratory analysis and rule development
    "validation",        # Held-out for intermediate tuning and sanity checks
    "test",              # Final untouched evaluation split
}


@dataclass
class ValidationIssue:
    document_id: str
    field_name: str
    severity: str  # "error", "warning"
    message: str


@dataclass
class DatasetValidationResult:
    is_valid: bool
    manifest_path: str
    total_documents: int
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "manifest_path": self.manifest_path,
            "total_documents": self.total_documents,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {"document_id": e.document_id, "field": e.field_name, "message": e.message}
                for e in self.errors
            ],
            "warnings": [
                {"document_id": w.document_id, "field": w.field_name, "message": w.message}
                for w in self.warnings
            ],
        }


def compute_sha256(file_path: Path | str) -> str:
    """Compute SHA-256 hash of a file's raw UTF-8 content."""
    p = Path(file_path)
    content = p.read_bytes()
    return hashlib.sha256(content).hexdigest()


def validate_dataset_manifest(
    manifest_path: Path | str,
    base_documents_dir: Path | str | None = None,
) -> DatasetValidationResult:
    """
    Validate dataset manifest against strict provenance and content integrity rules.
    """
    m_path = Path(manifest_path).resolve()
    if not m_path.exists():
        return DatasetValidationResult(
            is_valid=False,
            manifest_path=str(m_path),
            total_documents=0,
            errors=[ValidationIssue("manifest", "file", "error", f"Manifest file not found: {m_path}")],
        )

    try:
        manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
    except Exception as e:
        return DatasetValidationResult(
            is_valid=False,
            manifest_path=str(m_path),
            total_documents=0,
            errors=[ValidationIssue("manifest", "json", "error", f"Invalid JSON format: {e}")],
        )

    docs_root = Path(base_documents_dir).resolve() if base_documents_dir else m_path.parent
    documents = manifest_data.get("documents") or manifest_data.get("fixtures") or []

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    for doc in documents:
        doc_id = doc.get("id") or doc.get("file") or "unnamed_document"
        rel_file = doc.get("file") or doc.get("path")
        if not rel_file:
            errors.append(ValidationIssue(doc_id, "file", "error", "Missing 'file' or 'path' property"))
            continue

        file_path = docs_root / rel_file
        if not file_path.exists():
            # Check relative to manifest parent
            file_path = m_path.parent / rel_file
        if not file_path.exists():
            # Check relative to manifest parent / documents
            file_path = m_path.parent / "documents" / rel_file
        if not file_path.exists():
            errors.append(ValidationIssue(doc_id, "file", "error", f"File does not exist: {file_path}"))
            continue

        # Hash check
        expected_hash = doc.get("sha256") or doc.get("content_hash")
        actual_hash = compute_sha256(file_path)
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            errors.append(
                ValidationIssue(
                    doc_id,
                    "sha256",
                    "error",
                    f"SHA-256 hash mismatch. Expected {expected_hash}, calculated {actual_hash}",
                )
            )

        # Provenance status check
        prov_status = doc.get("provenance_status")
        if prov_status and prov_status not in VALID_PROVENANCE_STATUSES:
            errors.append(
                ValidationIssue(
                    doc_id,
                    "provenance_status",
                    "error",
                    f"Invalid provenance_status '{prov_status}'. Must be one of {sorted(list(VALID_PROVENANCE_STATUSES))}",
                )
            )

        # Origin label check
        origin_label = doc.get("ground_truth_origin") or doc.get("origin_label")
        if origin_label and origin_label not in VALID_ORIGIN_LABELS:
            errors.append(
                ValidationIssue(
                    doc_id,
                    "origin_label",
                    "error",
                    f"Invalid origin label '{origin_label}'. Must be one of {sorted(list(VALID_ORIGIN_LABELS))}",
                )
            )

        # Anti-misrepresentation integrity rule (Task 3 core rule)
        # Synthetic simulations must NOT be labeled as verified human authored
        is_synthetic_desc = (
            "synthetic" in doc.get("provenance_description", "").lower()
            or "simulat" in doc.get("provenance_description", "").lower()
            or doc.get("provenance_type", "").startswith("synthetic")
        )
        if is_synthetic_desc and prov_status == "verified" and origin_label == "human_authored":
            errors.append(
                ValidationIssue(
                    doc_id,
                    "provenance_integrity",
                    "error",
                    "Misrepresentation: Document described as synthetic simulation cannot have provenance_status='verified' and origin_label='human_authored'.",
                )
            )

        # Dataset split check
        split = doc.get("split")
        if split and split not in VALID_SPLITS:
            warnings.append(
                ValidationIssue(
                    doc_id,
                    "split",
                    "warning",
                    f"Unrecognized split '{split}'. Expected one of {sorted(list(VALID_SPLITS))}",
                )
            )

        # Provenance source tracking check
        if prov_status == "verified" and not doc.get("source_url") and not doc.get("source_citation"):
            warnings.append(
                ValidationIssue(
                    doc_id,
                    "source_verification",
                    "warning",
                    "Document marked as 'verified' without explicit 'source_url' or 'source_citation'.",
                )
            )

    is_valid = len(errors) == 0
    return DatasetValidationResult(
        is_valid=is_valid,
        manifest_path=str(m_path),
        total_documents=len(documents),
        errors=errors,
        warnings=warnings,
    )
