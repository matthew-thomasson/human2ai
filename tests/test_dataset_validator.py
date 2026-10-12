"""Unit tests for dataset metadata and provenance validator (M2.1)."""

import json
from pathlib import Path
import pytest

from md_audit.dataset_validator import (
    compute_sha256,
    validate_dataset_manifest,
)


def test_validator_detects_hash_mismatch(tmp_path: Path):
    doc_path = tmp_path / "sample.md"
    doc_path.write_text("# Hello World", encoding="utf-8")
    real_hash = compute_sha256(doc_path)

    manifest_data = {
        "version": "1.0.0",
        "documents": [
            {
                "id": "sample-01",
                "file": "sample.md",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "provenance_status": "documented",
                "ground_truth_origin": "human_authored",
                "provenance_description": "Test doc",
            }
        ],
    }
    m_path = tmp_path / "manifest.json"
    m_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    res = validate_dataset_manifest(m_path)
    assert res.is_valid is False
    assert any("hash mismatch" in e.message.lower() for e in res.errors)


def test_validator_detects_synthetic_misrepresentation(tmp_path: Path):
    doc_path = tmp_path / "fake_human.md"
    doc_path.write_text("# Simulated Student Essay\nWe went to the store.", encoding="utf-8")
    real_hash = compute_sha256(doc_path)

    # Improperly claiming synthetic simulation is verified human authored
    manifest_data = {
        "version": "1.0.0",
        "documents": [
            {
                "id": "fake-01",
                "file": "fake_human.md",
                "sha256": real_hash,
                "provenance_status": "verified",
                "ground_truth_origin": "human_authored",
                "provenance_description": "Synthetic simulation of human essay",
            }
        ],
    }
    m_path = tmp_path / "manifest.json"
    m_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    res = validate_dataset_manifest(m_path)
    assert res.is_valid is False
    assert any("misrepresentation" in e.message.lower() for e in res.errors)


def test_validator_passes_on_valid_manifest(tmp_path: Path):
    doc_path = tmp_path / "valid.md"
    doc_path.write_text("# Valid Document", encoding="utf-8")
    real_hash = compute_sha256(doc_path)

    manifest_data = {
        "version": "1.0.0",
        "documents": [
            {
                "id": "valid-01",
                "file": "valid.md",
                "sha256": real_hash,
                "provenance_status": "synthetic",
                "ground_truth_origin": "synthetic_simulation",
                "provenance_description": "Synthetic simulation of technical report",
                "split": "development",
            }
        ],
    }
    m_path = tmp_path / "manifest.json"
    m_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    res = validate_dataset_manifest(m_path)
    assert res.is_valid is True
    assert len(res.errors) == 0
