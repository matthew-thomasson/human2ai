"""Command-Line Interface for Markdown Writing Quality Auditor (md-audit)."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import yaml

from . import __version__
from .analyzers import (
    DeterministicAnalyzer,
    ModelEvaluator,
    analyze_burstiness,
    analyze_repetition,
)
from .editor import EditorialEngine
from .llm import LLMEditor, LLMReviewer, ModelError
from .reporting import (
    AuditReport,
    format_comparison_summary,
    format_json_report,
    format_markdown_report,
    format_terminal_summary,
)
from .scanner import scan_directory
from .scoring import QualityScorer
from .validation import SemanticPreservationGate


def get_default_config_path() -> Path:
    """Resolve bundled default config regardless of current working directory."""
    pkg_cfg = Path(__file__).resolve().parent / "config" / "default_config.yaml"
    if pkg_cfg.exists():
        return pkg_cfg
    repo_cfg = Path(__file__).resolve().parent.parent.parent / "config" / "default_config.yaml"
    if repo_cfg.exists():
        return repo_cfg
    return Path("config/default_config.yaml")


def get_default_rules_dir() -> Path:
    """Resolve bundled rules directory regardless of current working directory."""
    pkg_rules = Path(__file__).resolve().parent / "config" / "rules"
    if pkg_rules.exists():
        return pkg_rules
    repo_rules = Path(__file__).resolve().parent.parent.parent / "config" / "rules"
    if repo_rules.exists():
        return repo_rules
    return Path("config/rules")


def load_config(config_path: str | Path | None = None) -> dict:
    """Load configuration from specified file or fallback to package default."""
    if config_path:
        p = Path(config_path)
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        raise FileNotFoundError(f"Configuration file not found: {p}")

    default_p = get_default_config_path()
    if default_p.exists():
        return yaml.safe_load(default_p.read_text(encoding="utf-8")) or {}

    return {}


def run_audit(
    target_dir: str | Path,
    config: dict,
    rules_dir: str | Path | None = None,
    enable_model: bool = False,
    offline_model: bool = False,
    api_key: str | None = None,
) -> AuditReport:
    """Core audit execution helper shared by scan and compare commands."""
    exclusions = config.get("exclusions")
    documents = scan_directory(target_dir, exclusions=exclusions)

    if not rules_dir:
        rules_dir = get_default_rules_dir()

    deterministic_analyzer = DeterministicAnalyzer.from_rules_directory(rules_dir)
    scorer = QualityScorer(
        category_weights=config.get("scoring_weights"),
        severity_penalties=config.get("penalty_weights"),
    )

    doc_scores = []
    findings_by_file = {}
    model_evaluations = []

    model_evaluator = None
    if enable_model:
        m_cfg = config.get("model", {})
        model_evaluator = ModelEvaluator(
            base_url=m_cfg.get("base_url", "https://openrouter.ai/api/v1"),
            model=m_cfg.get("model", "openai/gpt-4o-mini"),
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
            offline_mode=offline_model,
        )

    for doc in documents:
        # 1. Deterministic rule analysis
        rule_findings = deterministic_analyzer.analyze(doc)

        # 2. Burstiness & Readability
        burstiness = analyze_burstiness(doc)
        rule_findings.extend(burstiness.findings)

        # 3. Repetition & Structural Cadence
        repetition = analyze_repetition(doc)
        rule_findings.extend(repetition.findings)

        rule_findings.sort(key=lambda f: (f.line_number, f.column))
        findings_by_file[doc.path] = rule_findings

        # Optional Model Evaluation
        doc_model_score = None
        if model_evaluator:
            m_res = model_evaluator.evaluate(doc)
            model_evaluations.append(m_res)
            doc_model_score = m_res.overall_score

        # 4. Score Document
        d_score = scorer.score_document(
            file_path=doc.path,
            word_count=doc.word_count,
            findings=rule_findings,
            burstiness=burstiness,
            repetition=repetition,
            model_score=doc_model_score,
        )
        doc_scores.append(d_score)

    dir_score = scorer.aggregate_directory(doc_scores)
    timestamp = datetime.now(timezone.utc).isoformat()

    return AuditReport(
        directory=str(target_dir),
        timestamp=timestamp,
        tool_version=__version__,
        ruleset_version="1.0.0",
        directory_score=dir_score,
        document_scores=doc_scores,
        findings_by_file=findings_by_file,
        model_evaluations=model_evaluations if enable_model else None,
        config_summary=config,
    )


def handle_scan(args: argparse.Namespace) -> int:
    """Handler for 'md-audit scan <directory>'."""
    config = load_config(args.config)
    try:
        report = run_audit(
            target_dir=args.directory,
            config=config,
            rules_dir=args.rules_dir,
            enable_model=args.model_eval,
            offline_model=args.offline,
            api_key=args.api_key,
        )
    except ModelError as e:
        print(f"Error during model-assisted evaluation: {e}", file=sys.stderr)
        return 1

    fmt = args.format.lower()
    if fmt == "json":
        json_data = format_json_report(report)
        import json
        text_out = json.dumps(json_data, indent=2)
    elif fmt in {"markdown", "md"}:
        text_out = format_markdown_report(report)
    else:
        text_out = format_terminal_summary(report)

    if args.output_report:
        out_p = Path(args.output_report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(text_out, encoding="utf-8")
        print(f"Report written to: {out_p.resolve()}")
    else:
        print(text_out)

    return 0


def handle_improve(args: argparse.Namespace) -> int:
    """Handler for 'md-audit improve <directory>'."""
    config = load_config(args.config)
    exclusions = config.get("exclusions")
    documents = scan_directory(args.directory, exclusions=exclusions)

    if not documents:
        print(f"No Markdown files found in {args.directory}.")
        return 0

    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY", "")

    # Setup LLM Editor if requested
    llm_editor = None
    if args.llm:
        editor_cfg = config.get("llm_editor", {})
        editor_model = args.model or editor_cfg.get("model", "deepseek/deepseek-chat")
        base_url = editor_cfg.get("base_url", "https://openrouter.ai/api/v1")
        llm_editor = LLMEditor(
            base_url=base_url,
            model=editor_model,
            api_key=api_key,
            offline_mode=args.offline,
        )

    # Setup Independent Reviewer if requested
    llm_reviewer = None
    if args.review:
        reviewer_cfg = config.get("reviewer", {})
        reviewer_model = args.reviewer_model or reviewer_cfg.get("model", "qwen/qwen-2.5-72b-instruct")
        base_url = reviewer_cfg.get("base_url", "https://openrouter.ai/api/v1")
        llm_reviewer = LLMReviewer(
            base_url=base_url,
            model=reviewer_model,
            api_key=api_key,
            offline_mode=args.offline,
        )

    engine = EditorialEngine(
        validator=SemanticPreservationGate(),
        llm_editor=llm_editor,
        llm_reviewer=llm_reviewer,
    )

    output_dir = Path(args.output or "revised")
    if not args.preview:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Improving Markdown documents from: {args.directory}")
    mode_str = f"LLM ({args.mode})" if args.llm else "Deterministic"
    if args.offline:
        mode_str += " [offline-simulation]"
    print(f"Engine mode: {mode_str}")
    if args.review:
        rev_model = args.reviewer_model or config.get("reviewer", {}).get("model", "qwen/qwen-2.5-72b-instruct")
        print(f"Reviewer: Enabled ({rev_model})")

    if args.preview:
        print("Mode: PREVIEW (no files will be written)\n")
    else:
        print(f"Output directory: {output_dir.resolve()}\n")

    improved_count = 0
    accepted_count = 0
    rejected_count = 0
    manual_review_count = 0
    unreviewed_count = 0

    for doc in documents:
        try:
            res = engine.improve_document(
                doc,
                use_llm=args.llm,
                mode=args.mode,
                run_review=args.review,
            )
        except ModelError as e:
            print(f"Error processing {doc.path} with LLM: {e}", file=sys.stderr)
            return 1

        content_to_write = doc.raw_content

        if not res.has_proposed_changes:
            print(f"[UNCHANGED] {doc.path} (already clean)")
        elif not res.validation.is_valid:
            # Deterministic preservation gate failed
            rejected_count += 1
            print(f"[REJECTED - SAFETY GATE] {doc.path}: Material changes detected.")
            for change in res.validation.material_changes:
                print(f"  - {change.change_type} ({change.severity}): {change.explanation}")
        elif args.review and res.review:
            dec = res.review.decision
            if dec == "Accept":
                accepted_count += 1
                improved_count += 1
                content_to_write = res.revised_content
                print(f"[REVISED [REVIEW: ACCEPTED]] {doc.path}")
                print(f"  Review verdict: Accept — {res.review.reason}")
                if args.preview or args.diff:
                    print(res.diff)
            elif dec == "Reject":
                rejected_count += 1
                print(f"[REJECTED [REVIEW: REJECTED]] {doc.path}")
                print(f"  Review verdict: Reject — {res.review.reason}")
            elif dec == "Review manually":
                manual_review_count += 1
                print(f"[MANUAL REVIEW REQUIRED] {doc.path}")
                print(f"  Review verdict: Review manually — {res.review.reason}")
            elif dec == "Unreviewed":
                unreviewed_count += 1
                print(f"[UNREVIEWED] {doc.path}")
                print(f"  Review verdict: Unreviewed — {res.review.reason}")
            else:
                unreviewed_count += 1
                print(f"[UNREVIEWED] {doc.path}")
                print(f"  Review verdict: {dec} — {res.review.reason}")
        else:
            # No review requested, safety gate passed
            improved_count += 1
            content_to_write = res.revised_content
            print(f"[REVISED] {doc.path}")
            if args.preview or args.diff:
                print(res.diff)

        if not args.preview:
            dest_file = output_dir / doc.path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(content_to_write, encoding="utf-8")

    print("\nEditorial Summary:")
    print(f"  Files processed: {len(documents)}")
    print(f"  Files improved:  {improved_count}")
    if args.review:
        print(f"  Accepted:        {accepted_count}")
        print(f"  Rejected:        {rejected_count}")
        print(f"  Manual review:   {manual_review_count}")
        print(f"  Unreviewed:      {unreviewed_count}")
    if not args.preview:
        print(f"  Output saved to: {output_dir.resolve()}")
    return 0


def handle_compare(args: argparse.Namespace) -> int:
    """Handler for 'md-audit compare <original-dir> <revised-dir>'."""
    config = load_config(args.config)

    orig_docs = {d.path: d for d in scan_directory(args.original_dir, exclusions=config.get("exclusions"))}
    rev_docs = {d.path: d for d in scan_directory(args.revised_dir, exclusions=config.get("exclusions"))}

    missing_in_revised = [p for p in orig_docs if p not in rev_docs]
    if missing_in_revised:
        print("Comparison Error: Missing files detected in revised directory!", file=sys.stderr)
        print("The following documents exist in the original directory but are missing from the revised directory:", file=sys.stderr)
        for p in sorted(missing_in_revised):
            print(f"  - {p}", file=sys.stderr)
        print("\nComparison aborted: revised directory is incomplete.", file=sys.stderr)
        return 1

    before_report = run_audit(args.original_dir, config=config)
    after_report = run_audit(args.revised_dir, config=config)

    orig_docs = {d.path: d for d in scan_directory(args.original_dir, exclusions=config.get("exclusions"))}
    rev_docs = {d.path: d for d in scan_directory(args.revised_dir, exclusions=config.get("exclusions"))}

    validator = SemanticPreservationGate()
    validation_results = {}
    diffs = {}
    files_changed = 0

    import difflib
    for rel_path, orig in orig_docs.items():
        if rel_path in rev_docs:
            rev = rev_docs[rel_path]
            val = validator.validate(orig.raw_content, rev.raw_content)
            validation_results[rel_path] = val
            if orig.raw_content != rev.raw_content:
                files_changed += 1
                diff_lines = list(
                    difflib.unified_diff(
                        orig.raw_lines,
                        rev.raw_lines,
                        fromfile=f"original/{rel_path}",
                        tofile=f"revised/{rel_path}",
                    )
                )
                diffs[rel_path] = "\n".join(diff_lines)

    summary_text = format_comparison_summary(
        before_report=before_report,
        after_report=after_report,
        files_changed=files_changed,
        diffs=diffs,
        validation_results=validation_results,
        output_dir=args.revised_dir,
    )

    if args.diff and diffs:
        summary_text += "\n\nFile Diffs:\n" + ("=" * 40) + "\n"
        for p, d in diffs.items():
            summary_text += f"\n--- {p} ---\n{d}\n"

    if args.output_report:
        out_p = Path(args.output_report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(summary_text, encoding="utf-8")
        print(f"Comparison report written to: {out_p.resolve()}")
    else:
        print(summary_text)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="md-audit",
        description="Markdown Writing Quality Auditor - POC",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan command
    scan_p = subparsers.add_parser("scan", help="Scan Markdown files and produce quality audit report")
    scan_p.add_argument("directory", help="Target directory containing Markdown files")
    scan_p.add_argument("--config", help="Path to custom config YAML")
    scan_p.add_argument("--rules-dir", help="Path to custom YAML rules directory")
    scan_p.add_argument("--format", choices=["text", "markdown", "json", "md"], default="text", help="Output format")
    scan_p.add_argument("--output-report", help="File path to save the generated report")
    scan_p.add_argument("--model-eval", action="store_true", help="Enable optional model-assisted critique")
    scan_p.add_argument("--offline", action="store_true", help="Run in offline simulation mode")
    scan_p.add_argument("--api-key", help="OpenRouter API key override")

    # improve command
    imp_p = subparsers.add_parser("improve", help="Propose and apply targeted editorial improvements")
    imp_p.add_argument("directory", help="Target directory to improve")
    imp_p.add_argument("--output", default="revised", help="Output directory for revised files (default: ./revised)")
    imp_p.add_argument("--preview", action="store_true", help="Preview proposed edits without writing files")
    imp_p.add_argument("--diff", action="store_true", help="Display full unified diff of changes")
    imp_p.add_argument("--config", help="Path to custom config YAML")
    imp_p.add_argument("--llm", action="store_true", help="Use OpenRouter LLM for contextual rewriting")
    imp_p.add_argument("--mode", choices=["conservative", "balanced"], default="balanced", help="LLM editing mode (default: balanced)")
    imp_p.add_argument("--model", help="LLM rewriting model (e.g. deepseek/deepseek-chat)")
    imp_p.add_argument("--review", action="store_true", help="Use a second independent LLM to review proposed changes")
    imp_p.add_argument("--reviewer-model", help="Reviewer LLM model (e.g. qwen/qwen-2.5-72b-instruct)")
    imp_p.add_argument("--offline", action="store_true", help="Run LLM rewriter and reviewer in offline simulation mode")
    imp_p.add_argument("--api-key", help="OpenRouter API key override")

    # compare command
    cmp_p = subparsers.add_parser("compare", help="Compare writing quality before and after improvement")
    cmp_p.add_argument("original_dir", help="Original Markdown directory")
    cmp_p.add_argument("revised_dir", help="Revised Markdown directory")
    cmp_p.add_argument("--config", help="Path to custom config YAML")
    cmp_p.add_argument("--output-report", help="File path to save comparison report")
    cmp_p.add_argument("--diff", action="store_true", help="Include full unified diffs in output")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for CLI execution."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return handle_scan(args)
    elif args.command == "improve":
        return handle_improve(args)
    elif args.command == "compare":
        return handle_compare(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
