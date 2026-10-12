# Research and Component Evaluation

This document evaluates the existing projects specified in Section 2 of the Development Brief for the **Markdown Writing Quality Auditor (POC)**.

---

## 1. Project Evaluations

### A. Agent Skills

#### 1. apoapostolov/humanizer
- **Repository**: [https://github.com/apoapostolov/humanizer](https://github.com/apoapostolov/humanizer)
- **License**: MIT
- **Maintenance Status**: Actively maintained (multi-version suite releases up through 2026, e.g., v2.12.x).
- **Direct Rule Reuse**: High. Contains `skills/ai-writing-detector` with deterministic regex engines, a Vale review gate in `skills/writing-prose`, and strict rewrite preservation validators.
- **CLI / Agent Harness**: Employs Node.js CLI scripts (`node scripts/analyze.js`) and agent skill instructions.
- **Diagnostics & Scores**: Generates 0–100 signal indicators, categorized markers, and explicitly avoids fake authorship claims or classifier laundering.
- **Editorial Rewriting**: Supported via `humanizer` and `simple-english` skills using register-aware voice targeting.
- **Dependencies**: Node.js (>= 18) for native scripts, or LLM agent harnesses.

#### 2. shir-danishyar/humanize
- **Repository**: [https://github.com/shir-danishyar/humanize](https://github.com/shir-danishyar/humanize)
- **License**: MIT
- **Maintenance Status**: Actively maintained.
- **Direct Rule Reuse**: Very High. Catalogues 39 numbered structural patterns (P1–P39) in `references/patterns.md` and chronological model-era vocabulary shifts (2023–2024 GPT-4, 2024–2025 GPT-4o, 2025+ GPT-5) in `references/vocabulary.md`, grounded in Wikipedia "Signs of AI writing" and published corpus studies (Kobak et al., Juzek & Ward, Reinhart et al.).
- **CLI / Agent Harness**: Designed for AI coding harnesses (Claude Code, Cursor, Copilot, Codex).
- **Diagnostics & Scores**: Emphasizes pattern clustering/density over single hits, burstiness, and concrete vs. vague language.
- **Editorial Rewriting**: Clear rules for "Rewrite mode": preserves direct quotes, citations, numbers, dates, URLs, code fences, and proper nouns without introducing invented facts.
- **Dependencies**: Pure Markdown rules and references; zero external runtime dependencies.

#### 3. Aboudjem/humanizer-skill
- **Repository**: [https://github.com/Aboudjem/humanizer-skill](https://github.com/Aboudjem/humanizer-skill)
- **License**: MIT
- **Maintenance Status**: Actively maintained.
- **Direct Rule Reuse**: High. Details 55 AI writing habits, 5 voice profiles, and measurable signals.
- **CLI / Agent Harness**: Invokable via `npx skills add` or Claude Code plugins.
- **Diagnostics & Scores**: Computes a 0–100 score based on four measurable signals (burstiness / sentence length variance, pattern density, perplexity markers) rather than simple naive counts.
- **Editorial Rewriting**: Preserves facts and tone across five distinct voice profiles while operating 100% locally.
- **Dependencies**: Node / npx or Claude plugin runtime.

#### 4. ameenmo/humanize-skill
- **Repository**: [https://github.com/ameenmo/humanize-skill](https://github.com/ameenmo/humanize-skill)
- **License**: MIT
- **Maintenance Status**: Actively maintained.
- **Direct Rule Reuse**: Very High. Offers detailed checklists in `references/editing-checklists.md` and `references/ai-slop-tells.md` (lexical tells, phrase/cliché tells, and structural tells such as negative parallelism "not X, but Y", compulsive rule of three, topic-sentence-support-restate, trailing participles, throat-clearing openers).
- **CLI / Agent Harness**: Designed for agent harnesses (Claude Code, Cursor, Codex).
- **Diagnostics & Scores**: Strictly enforces: "Never issue a verdict on who or what wrote the draft... say the writing problem, never the provenance." Focuses on human readability rather than detector evasion.
- **Editorial Rewriting**: Clear bifurcation into "Preserve" mode (strip machine-default phrasing, retain author's voice) and "Conform" mode. Strictly protects numbers, citations, and placeholders.
- **Dependencies**: Markdown ruleset.

---

### B. Supporting Tools

#### 5. vale-cli/vale
- **Repository**: [https://github.com/vale-cli/vale](https://github.com/vale-cli/vale)
- **License**: MIT
- **Maintenance Status**: Actively maintained (compiled Go binary).
- **Direct Rule Reuse**: High. Vale's YAML rule format (`extends: existence`, `extends: substitution`, `extends: regex`) is the recognized open standard for declarative prose linting rules.
- **CLI / Agent Harness**: Native standalone CLI executable (`vale path/to/doc.md`).
- **Diagnostics & Scores**: Provides precise file, line, column, rule ID, severity (suggestion, warning, error), and substitution recommendations. Does not natively calculate an aggregate 0–100 quality score.
- **Editorial Rewriting**: Diagnostic prose linting only; does not perform semantic rewrites.
- **Dependencies**: Compiled Go binary (requires OS-level installation or package manager).

#### 6. promptfoo/promptfoo
- **Repository**: [https://github.com/promptfoo/promptfoo](https://github.com/promptfoo/promptfoo)
- **License**: MIT
- **Maintenance Status**: Actively maintained.
- **Direct Rule Reuse**: Moderate. Evaluates prompts and outputs using assertions (`llm-rubric`, regex, model grading).
- **CLI / Agent Harness**: CLI tool (`npx promptfoo eval`). Supports OpenRouter and hundreds of LLM providers.
- **Diagnostics & Scores**: High diagnostic value for prompt grading and side-by-side model comparisons, but acts as an evaluation test harness rather than an in-situ Markdown document scanner.
- **Editorial Rewriting**: Evaluates rewrites, but is not designed for inline document restructuring.
- **Dependencies**: Node.js (>= 18) and npm.

#### 7. textlint/textlint
- **Repository**: [https://github.com/textlint/textlint](https://github.com/textlint/textlint)
- **License**: MIT
- **Maintenance Status**: Actively maintained.
- **Direct Rule Reuse**: Moderate. AST-based Markdown linter (`TxtAST`) ensuring code fences and URLs are ignored during prose linting.
- **CLI / Agent Harness**: Node.js CLI tool (`npx textlint`).
- **Diagnostics & Scores**: AST-level error and warning diagnostics.
- **Editorial Rewriting**: Provides `--fix` for mechanical token substitutions, but lacks contextual editorial rewriting capabilities.
- **Dependencies**: Node.js and npm ecosystem.

---

## 2. Synthesis and Selection Decision

| Component Selected | Reused From | Rationale |
|---|---|---|
| **Deterministic Rule Engine** | Vale YAML syntax + `shir-danishyar/humanize` + `ameenmo/humanize-skill` | Standardized declarative YAML format (inspired by Vale) with comprehensive, curated pattern lists (39 structural patterns, era-based vocabulary, phrase clichés, wordy constructions, and passive voice). Eliminates heavy Node.js or Go binary dependencies while remaining 100% compatible with existing rule definitions. |
| **Burstiness & Readability Metric** | `Aboudjem/humanizer-skill` + Flesch Reading Ease | Measures sentence-length variance (standard deviation / coefficient of variation) to capture uniform sentence cadence (a hallmark of AI generation) without relying on fragile heuristic guesses. |
| **Semantic Preservation Gate** | `apoapostolov/humanizer` + `ameenmo/humanize-skill` | Hard safety gate that deterministically extracts and verifies numbers, dates, RFC-2119 keywords, code blocks, URLs, and technical terms before any rewrite is accepted. Any material discrepancy causes immediate rejection. |
| **Editorial Rewriting Engine** | `shir-danishyar/humanize` + `ameenmo/humanize-skill` | "Preserve mode" philosophy: removes formulaic fluff and improves active voice without editorializing, inventing facts, or touching code blocks and links. |
| **Model-Assisted Critic** | OpenRouter API / Promptfoo evaluation rubrics | Lightweight, optional model evaluation acting as an independent critic with configurable provider, prompt rubrics, and an offline mock mode. |
| **Scoring & Reporting Model** | Brief specification + `apoapostolov` signal philosophy | Transparent 0–100 writing quality score across 5 categories, normalized by document length. Explicitly disclaims fake authorship probability. Outputs Terminal summary, Markdown report, and structured JSON. |
