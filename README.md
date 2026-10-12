# Markdown Writing Quality Auditor (`md-audit`) — POC

> **Proof of Concept:** A lightweight, explainable command-line auditor for Markdown (`.md`) documentation that detects synthetic AI writing habits, scores writing quality transparently, applies targeted editorial improvements, and enforces strict semantic preservation.

---

## 1. Overview & Mission

Generative AI models produce predictable stylistic fingerprints: formulaic introductions, inflated significance puffery ("stands as a testament to", "plays a pivotal role"), negative parallelism ("it's not X, it's Y"), repetitive formal connectives ("Moreover", "Furthermore"), and flat sentence length distributions (low burstiness).

`md-audit` provides an automated editorial workflow that:
- **Recursively audits** Markdown repositories for AI writing patterns, wordiness, repetition, and cadence.
- **Emits an explainable 0–100 Writing Quality Score** across five distinct categories without relying on deceptive AI-authorship probabilities.
- **Proposes targeted editorial rewrites** to make writing direct, active, and human.
- **Enforces a strict Semantic Preservation Gate** to guarantee numbers, dates, RFC-2119 requirements, code blocks, URLs, and identifiers are never altered or hallucinated.
- **Measures before/after deltas** with side-by-side comparison tables.

---

## 2. Research & Reused Components

Rather than reinventing writing rules, `md-audit` synthesizes open-source Agent Skills and industry-standard prose linters:

| Component | Upstream Source | License | Reused Capability |
|---|---|---|---|
| **Deterministic Rule Engine** | Vale YAML specification | MIT | Standardized declarative YAML rules (`config/rules/*.yaml`) covering AI clichés, formulaic openers/closers, negative parallelism, wordiness, and passive voice. |
| **AI Tells & Lexical Catalog** | `shir-danishyar/humanize` & `ameenmo/humanize-skill` | MIT | 39 structural pattern definitions, chronological model vocabulary shifts (GPT-4, GPT-4o, GPT-5), and cliché tell banks distilled from Wikipedia "Signs of AI writing" and published corpus studies (Kobak et al. 2025, Juzek & Ward 2025, Reinhart et al. 2025). |
| **Burstiness & Rhythm Metric** | `Aboudjem/humanizer-skill` | MIT | Coefficient of variation ($CV = \sigma / \mu$) metric measuring sentence-length variance to catch flat, robotic sentence pacing. |
| **Semantic Preservation Gate** | `apoapostolov/humanizer` | MIT | Protected-span validation algorithms ensuring code fences, technical parameters, URLs, and requirements cannot be mutated by an editor. |
| **Model-Assisted Critic** | OpenRouter / Promptfoo evaluation rubrics | MIT | Independent model critic evaluating naturalness, technical precision, and logical coherence, with a 100% offline simulation mode for local testing. |

A full comparative evaluation across maintenance status, dependencies, and rule compatibility is documented in [docs/research_evaluation.md](docs/research_evaluation.md).

---

## 3. Installation & Quick Start

### Prerequisites
- Python 3.9+
- Zero external binary or Node.js dependencies required.

### Installation
Clone the repository and install in editable mode:

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

## 4. CLI Commands & Usage

### A. Scanning a Directory (`scan`)
Recursively discovers `.md` files (automatically ignoring `.git`, `node_modules`, virtual environments, and build artifacts) and produces an audit summary:

```bash
md-audit scan ./my-docs
```

#### Terminal Summary Example:
```text
Markdown Quality Audit
======================

Directory: ./my-docs
Files analysed: 5

Overall writing quality: 89/100

Category scores:
  AI-style patterns        73/100
  Readability              95/100
  Repetition               94/100
  Language clarity         88/100
  Consistency             100/100

Highest-priority findings:

ai_technical.md
  - [WARNING] L1: Overly uniform sentence structures (burstiness CV: 0.28 < 0.40).
  - [WARNING] L3: 'stands as a testament to' is formulaic significance puffery.
  - [SUGGESTION] L5: 'crucial' is heavily overused by LLMs to create artificial importance.
  - [ERROR] L7: Negative parallelism ('It's not X, it's Y') is a prominent AI rhetorical pattern.

Result: 4 file(s) have editorial improvement opportunities.

Note: Scores reflect writing quality, stylistic clarity, and natural cadence. They do NOT represent an AI-authorship probability or detector verdict.
```

#### Output Formats & Reports:
Export detailed Markdown or machine-readable JSON reports to external paths:

```bash
# Generate Markdown report
md-audit scan ./my-docs --format markdown --output-report ./reports/audit.md

# Generate structured JSON report for CI/CD automation
md-audit scan ./my-docs --format json --output-report ./reports/audit.json

# Enable optional model-assisted critic (uses OpenRouter or offline simulation)
md-audit scan ./my-docs --model-eval --offline
```

---

### B. Proposing and Applying Improvements (`improve`)
Applies targeted editorial revisions that eliminate fluff, formulaic openers, and wordy constructions while strictly protecting technical data:

```bash
# Preview proposed changes as a unified diff without modifying files
md-audit improve ./my-docs --preview --diff

# Write revised documents to a separate output directory (never overwrites originals)
md-audit improve ./my-docs --output ./revised --diff
```

---

### C. Rescoring and Comparing Results (`compare`)
Reruns the quality audit across both original and revised directories to measure concrete quality gains and audit semantic preservation:

```bash
md-audit compare ./my-docs ./revised --output-report ./reports/comparison.md
```

#### Comparison Output Example:
```text
Writing Quality Comparison
==========================

Original directory: ./my-docs
Revised directory:  ./revised

Overall writing quality: 89 -> 95 (+6)

| Metric               | Before |  After | Change |
|----------------------|--------:|--------:|--------:|
| Writing quality      |     89 |     95 |     +6 |
| AI-style patterns    |     73 |     92 |    +19 |
| Readability          |     95 |     94 |     -1 |
| Repetition           |     94 |     98 |     +4 |
| Language clarity     |     88 |     93 |     +5 |
| Consistency          |    100 |    100 |     +0 |

Files modified:              4
Initial findings count:      38
Resolved findings:           19
Remaining findings:          19

Semantic Preservation Audit:
  [PASSED] ai_technical.md: All numbers, dates, code blocks, and RFC keywords preserved.
  [PASSED] good_technical.md: All numbers, dates, code blocks, and RFC keywords preserved.
  [PASSED] markdown_features.md: All numbers, dates, code blocks, and RFC keywords preserved.
  [PASSED] numerical_requirements.md: All numbers, dates, code blocks, and RFC keywords preserved.
  [PASSED] repetitive_marketing.md: All numbers, dates, code blocks, and RFC keywords preserved.
```

---

## 5. Scoring Model & Rubric

The overall score is a **Writing Quality Score (0–100)** where higher is better.

### Category Weights
- **AI-Style Patterns (25%):** Penalties for AI clichés, formulaic introductions/conclusions, and negative parallelism.
- **Readability & Cadence (20%):** Evaluates sentence length variation ($CV$), Flesch Reading Ease, and overly uniform sentence structures.
- **Repetition (20%):** Penalizes repetitive transitional adverbs ("Moreover", "Furthermore") and repetitive sentence openers.
- **Language Clarity (20%):** Penalizes wordiness ("in order to" $\rightarrow$ "to"), generic adjectives ("pivotal", "transformative"), and passive constructions.
- **Consistency (15%):** Penalizes contradictory technical spelling variants (e.g., mixing "front-end" and "frontend").

### Length-Normalized Density
To ensure document length does not unfairly dominate scores, penalties are scaled using sublinear word count normalization:
$$\text{Penalty} = \frac{\sum \text{Severity Penalties}}{\max(120, \text{Word Count})^{0.65}} \times 22.0$$

### Directory Aggregation
Directory scores are aggregated via a **word-count-weighted average**, ensuring that large documents contribute proportionally and tiny stubs do not distort aggregate ratings:
$$\text{Directory Score} = \frac{\sum_i (\text{Score}_i \times \text{Words}_i)}{\sum_i \text{Words}_i}$$

---

## 6. Semantic Preservation Gate

Before any editorial change is committed or suggested, `md-audit` subjects the diff to a strict deterministic preservation gate (`src/md_audit/validation.py`):

1. **Numerical Values:** Multi-set comparison of integers, decimals, percentages, port numbers, memory sizes, and version strings. Dropping or altering numbers (e.g. `99.95%` $\rightarrow$ `99.9%` or port `8080` $\rightarrow$ `80`) triggers a **CRITICAL** rejection.
2. **Dates & Deadlines:** ISO dates (`2026-11-15`) and textual dates (`October 20, 2026`) must match verbatim.
3. **RFC-2119 Requirements:** Keywords (`MUST`, `MUST NOT`, `REQUIRED`, `SHALL`, `SHOULD`) cannot be dropped or weakened.
4. **Code Blocks:** Fenced code blocks (`` ``` ``) and their internal contents are isolated and kept byte-for-byte identical.
5. **Technical Identifiers & URLs:** Backticked inline code (`` `flag` ``) and target URLs (`https://...`) cannot be mutated.
6. **Markdown Structure:** Table column structures and heading hierarchies are preserved.

If any critical discrepancy is detected, the edit is aborted and flagged with an explanation.

---

## 7. Model-Assisted Critic (OpenRouter)

For deep semantic review, `md-audit` supports an optional LLM critic compatible with OpenRouter and OpenAI:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
md-audit scan ./my-docs --model-eval
```

Configuration in `config/default_config.yaml`:
```yaml
model:
  enabled: true
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  model: "openai/gpt-4o-mini"
  temperature: 0.2
  offline_mode: false
```

- **Independent Critic:** Evaluates naturalness, audience purpose, logical coherence, and unsubstantiated claims without rewriting.
- **Offline Simulation Mode (`--offline`):** Deterministic mock critic that runs locally without an API key or network access for tests and air-gapped environments.

---

## 8. Test Suite

Run the full automated test suite with pytest:

```bash
pytest -vv
```

The test suite covers:
- Markdown prose masking and code fence isolation
- Exclusion filter verification (`.git`, `node_modules`, `venv`)
- Deterministic rule detections and line/column tracking
- Burstiness and Flesch readability calculations
- Scoring formula bounds and directory weighting
- Semantic preservation failure modes (number alteration, RFC keyword tampering, code fence modification, URL mutations)
- CLI subcommands (`scan`, `improve`, `compare`) across text, markdown, and JSON formats.

---

## 9. Limitations & Next Steps

### Current Limitations
- **Syntax Scope:** Designed for CommonMark / GitHub Flavored Markdown (`.md`). Custom non-standard markdown extensions (e.g., custom MDX JSX tags) may require additional parser plugins.
- **Grammar Mechanics:** Focuses on stylistic clarity, AI tells, and semantic preservation rather than general spell-checking.
- **LLM Rewrite Latency:** While rule-based improvements execute in milliseconds, large-scale multi-file LLM revisions depend on OpenRouter endpoint throughput and token quotas.

### Next Steps
1. **Vale Style Exporter:** Add a command (`md-audit export-vale`) to export `config/rules/*.yaml` directly into Vale `.vale.ini` style packs.
2. **Interactive TUI Mode:** Interactive terminal diff approval (similar to `git add -p`) allowing users to accept or decline individual paragraph suggestions interactively.
3. **Custom House Voice Profiles:** Allow loading custom tone guides (e.g. `HUMANIZE_STYLE.md`) to support domain-specific jargon allowlists.
