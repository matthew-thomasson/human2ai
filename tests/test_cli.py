"""Integration tests for CLI commands."""

import json
from pathlib import Path
from md_audit.cli import main


def test_cli_scan_text(capsys):
    ret = main(["scan", "fixtures"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Markdown Quality Audit" in captured
    assert "Overall writing quality:" in captured


def test_cli_scan_json(capsys):
    ret = main(["scan", "fixtures", "--format", "json"])
    assert ret == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "summary" in data
    assert "overall_writing_quality" in data["summary"]
    assert "documents" in data


def test_cli_scan_markdown(capsys):
    ret = main(["scan", "fixtures", "--format", "markdown"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "# Markdown Quality Audit Report" in captured
    assert "Executive Summary" in captured


def test_cli_scan_offline_model(capsys):
    ret = main(["scan", "fixtures", "--model-eval", "--offline"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Model-assisted evaluation" in captured


def test_cli_improve_preview(capsys):
    ret = main(["improve", "fixtures", "--preview", "--diff"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "PREVIEW" in captured
    assert "Editorial Summary" in captured


def test_cli_compare(tmp_path: Path, capsys):
    # Run improve to temporary directory
    revised_dir = tmp_path / "revised"
    ret_imp = main(["improve", "fixtures", "--output", str(revised_dir)])
    assert ret_imp == 0

    # Compare
    ret_cmp = main(["compare", "fixtures", str(revised_dir)])
    assert ret_cmp == 0
    captured = capsys.readouterr().out
    assert "Writing Quality Comparison" in captured
    assert "Semantic Preservation Audit:" in captured
