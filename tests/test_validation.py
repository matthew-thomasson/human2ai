"""Tests for Semantic Preservation Gate."""

from md_audit.validation import SemanticPreservationGate


def test_validation_passes_on_pure_prose_edit():
    original = (
        "# System Config\n"
        "In order to initialize the node, run `start_node` on port 8080.\n"
        "The deadline is 2026-11-15. Clients MUST retry 3 times.\n"
        "See [docs](https://example.com/api)."
    )
    # Editorial change: "In order to" -> "To", but all protected facts (port 8080, 2026-11-15, MUST, 3, URL, `start_node`) kept verbatim
    revised = (
        "# System Config\n"
        "To initialize the node, run `start_node` on port 8080.\n"
        "The deadline is 2026-11-15. Clients MUST retry 3 times.\n"
        "See [docs](https://example.com/api)."
    )
    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert result.is_valid
    assert len(result.material_changes) == 0


def test_validation_rejects_altered_numbers():
    original = "System availability target is 99.95% with 3 retries on port 8080."
    # Altered 99.95% to 99.9%
    revised = "System availability target is 99.9% with 3 retries on port 8080."

    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert not result.is_valid
    crit_types = [c.change_type for c in result.material_changes if c.severity == "critical"]
    assert "numerical_value" in crit_types


def test_validation_rejects_altered_dates():
    original = "Audit logs must be archived by 2026-11-15."
    # Changed date
    revised = "Audit logs must be archived by 2026-12-01."

    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert not result.is_valid
    crit_types = [c.change_type for c in result.material_changes if c.severity == "critical"]
    assert "date_or_deadline" in crit_types


def test_validation_rejects_weakened_rfc_requirements():
    original = "All backend services MUST support TLS 1.3 encryption."
    # Weakened MUST to SHOULD
    revised = "All backend services SHOULD support TLS 1.3 encryption."

    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert not result.is_valid
    crit_types = [c.change_type for c in result.material_changes if c.severity == "critical"]
    assert "technical_requirement" in crit_types


def test_validation_rejects_altered_code_blocks():
    original = (
        "Run the following script:\n"
        "```bash\n"
        "python deploy.py --env prod\n"
        "```\n"
    )
    # Code block modified
    revised = (
        "Run the following script:\n"
        "```bash\n"
        "python deploy.py --env staging\n"
        "```\n"
    )

    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert not result.is_valid
    crit_types = [c.change_type for c in result.material_changes if c.severity == "critical"]
    assert "code_block" in crit_types


def test_validation_rejects_altered_urls():
    original = "Read the [API Guide](https://example.com/v1/docs)."
    # URL changed or dropped
    revised = "Read the [API Guide](https://example.com/v2/new-docs)."

    gate = SemanticPreservationGate()
    result = gate.validate(original, revised)
    assert not result.is_valid
    crit_types = [c.change_type for c in result.material_changes if c.severity == "critical"]
    assert "url_or_link" in crit_types
