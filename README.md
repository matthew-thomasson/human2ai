# Markdown Writing Quality Auditor (`md-audit`) — Enhanced POC

> **A practical local Markdown writing-quality tool** that audits documentation for synthetic AI patterns, provides an explainable 0–100 quality score, offers optional contextual LLM rewriting, supports an independent secondary reviewer, and guarantees strict semantic preservation.

---

## 1. Key Capabilities

1. **Local Markdown Quality Audit (`scan`)**: Recursively discovers Markdown files, detects formulaic AI clichés, analyzes sentence rhythm (burstiness), checks repetition and passive voice, and calculates a length-normalized 0–100 quality score.
2. **Contextual LLM Rewriting (`improve --llm`)**: Understands document context to eliminate fluff, improve natural flow, and remove AI idioms without altering meaning. Supports **Conservative** and **Balanced** editing modes. Automatically chunks long files by Markdown headings to avoid truncation.
3. **Deterministic Editorial Mode (`improve`)**: Fast, zero-dependency local substitutions with dynamic casing preservation and safe clause handling.
4. **Independent Model Reviewer (`--review`)**: A second configurable model (e.g., Qwen evaluating DeepSeek's rewrites) verifies whether naturalness improved and whether any technical meaning changed, issuing **Accept**, **Reject**, or **Review manually** decisions. If the reviewer is unavailable, edits are marked **Unreviewed**.
5. **Deterministic Semantic Preservation Gate**: Protected-span validator verifying numbers, dates, RFC-2119 keywords, code blocks, URLs, and Markdown structure. Material changes cause automated rejection.
6. **Rescoring & Comparison (`compare`)**: Side-by-side delta reporting showing score gains, resolved issues, reviewer decisions, and unified diffs.

---

## 2. Installation & Portability

### Prerequisites
- Python 3.9+
- Zero external binary or Node.js dependencies required. Bundled rules and default configuration work out of the box from any directory.

### Installation
```bash
git clone https://github.com/matthew-thomasson/human2ai.git
cd human2ai
pip install -e .
```

Verify installation:
```bash
md-audit --version
md-audit --help
```

---

## 3. CLI Commands & Workflows

### A. Scanning a Directory (`scan`)
Audit prose quality and produce terminal, Markdown, or JSON reports:

```bash
# Scan a directory (ignores .git, node_modules, .venv, etc.)
md-audit scan ./docs

# Generate detailed Markdown or JSON report
md-audit scan ./docs --format markdown --output-report ./reports/audit.md
md-audit scan ./docs --format json --output-report ./reports/audit.json

# Optional model-assisted critique (independent critic)
md-audit scan ./docs --model-eval
md-audit scan ./docs --model-eval --offline   # Offline test simulation mode
```

---

### B. Editorial Improvement (`improve`)

#### 1. Deterministic Rule-Based Mode (Fast, Local)
Applies safe substitutions (removing wordy filler like "in order to" $\rightarrow$ "to", stripping clichéd openers like "In today's fast-paced world," while preserving capitalization of subsequent words):

```bash
# Preview diff without writing files
md-audit improve ./docs --preview --diff

# Write revised files to a separate output directory
md-audit improve ./docs --output ./revised
```

#### 2. Contextual LLM Rewriting Mode (`--llm`)
Uses OpenRouter to rewrite prose while isolating code blocks and links with non-colliding token placeholders:

```bash
# Balanced mode (default: substantial flow, clarity, and active voice improvements)
md-audit improve ./docs --llm --mode balanced --output ./revised

# Conservative mode (minimal targeted edits focusing on obvious weaknesses)
md-audit improve ./docs --llm --mode conservative --output ./revised

# Custom model specification (e.g., DeepSeek, Claude, GPT)
md-audit improve ./docs --llm --model deepseek/deepseek-chat --output ./revised
```

#### 3. Adding an Independent Reviewer (`--review`)
Uses a second LLM to evaluate proposed rewrites before accepting them:

```bash
# DeepSeek edits, Qwen reviews
md-audit improve ./docs \
  --llm --model deepseek/deepseek-chat \
  --review --reviewer-model qwen/qwen-2.5-72b-instruct \
  --output ./revised

# Offline simulation mode for automated tests and air-gapped runs
md-audit improve ./docs --llm --review --offline --output ./revised
```

If the reviewer rejects a change, the original passage is retained and the rejection reason is logged. If the reviewer is unavailable, the edit is flagged as **Unreviewed**.

---

### C. Rescoring and Comparing Results (`compare`)
Compares the original directory against revised files:

```bash
md-audit compare ./docs ./revised
md-audit compare ./docs ./revised --diff --output-report ./reports/comparison.md
```

#### Comparison Summary Format:
```text
Markdown Quality Comparison
===========================
Files analysed: 18
Files improved: 12
Overall quality:
  Before: 74/100
  After:  87/100 (+13)
AI-style patterns:
  Before: 65/100
  After:  91/100 (+26)
Changes:
  Accepted:   34
  Rejected:   3
  Unreviewed: 2
Technical preservation:
  No detected changes to protected elements.
Output: ./revised
```

---

## 4. Configuration

Default settings in `config/default_config.yaml` can be customized or overridden via `--config path/to/config.yaml`:

```yaml
# Exclusion paths
exclusions:
  - ".git"
  - "node_modules"
  - ".venv"
  - "build"
  - "dist"
  - "revised"

# Scoring weights across the 5 categories
scoring_weights:
  ai_patterns: 0.25
  readability: 0.20
  repetition: 0.20
  language_clarity: 0.20
  consistency: 0.15

# LLM Contextual Rewriter
llm_editor:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  model: "deepseek/deepseek-chat"
  mode: "balanced"
  temperature: 0.3
  chunk_threshold_chars: 4000

# Independent LLM Reviewer
reviewer:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  model: "qwen/qwen-2.5-72b-instruct"
  temperature: 0.1

# Semantic Preservation validation gates
validation:
  strict_numbers: true
  strict_dates: true
  strict_technical_requirements: true
  strict_code_blocks: true
  strict_urls: true
  strict_markdown_structure: true
```

Set your OpenRouter API key:
```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
# Or on Windows PowerShell:
$env:OPENROUTER_API_KEY = "sk-or-v1-..."
```

---

## 5. Semantic Preservation & Safety

The Semantic Preservation Gate (`src/md_audit/validation.py`) deterministically inspects every edit:
1. **Numbers:** All integers, decimals, percentages, port numbers, and units (`99.95%`, `port 8080`, `150ms`, `v2.4.1`) must remain identical in value and count.
2. **Dates & Deadlines:** ISO and textual dates (`2026-11-15`, `October 20, 2026`) must be preserved.
3. **RFC-2119 Keywords:** Requirements (`MUST`, `MUST NOT`, `SHALL`, `REQUIRED`, `SHOULD`) cannot be dropped or weakened.
4. **Code Blocks & Inline Code:** Fenced blocks (`` ``` ``) and inline backticks (`` `identifier` ``) are isolated with token placeholders and verified byte-for-byte.
5. **Links & Tables:** Target URLs and table structures cannot be corrupted.

Any violation triggers immediate rejection with file and line diagnostics.

---

## 6. Testing

Run the automated test suite with pytest:

```bash
pytest -vv
```

All 37 unit and integration tests execute in under 0.5s:
- Safe regex substitutions & casing preservation
- Markdown preservation (code fences, inline code, links, tables)
- Model API failure handling (raising `ModelError` explicitly without silent mock fallback)
- Independent reviewer decisions (Accept, Reject, Review manually, Unreviewed)
- Long document section splitting
- Portability of bundled configuration and rules
- End-to-end `scan`, `improve`, and `compare` workflows

---

## 7. Scope & Limitations

- **Personal Local Tool:** Designed for developers auditing Markdown documentation locally or in CI scripts.
- **CommonMark / GFM:** Tailored for standard GitHub Flavored Markdown.
- **Cost Efficiency:** Deterministic mode incurs $0.00. LLM rewriting and review runs on OpenRouter with economical models (~$0.01 per 25,000 words).
