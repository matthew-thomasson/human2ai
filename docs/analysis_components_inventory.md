# Analysis Components Inventory — human2ai (`md-audit`)

**Engine Repository:** `matthew-thomasson/human2ai`  
**Tool Version:** `0.1.0`  
**Environment / Installed Dependencies:**
- Python: `3.12.10`
- `PyYAML`: `6.0.3` (used for declarative YAML rule configuration loading)
- `requests`: `2.34.2` (used for HTTP API communication with OpenRouter LLM endpoints)
- `pytest`: `9.1.1` (development / testing test runner)
- *Note on detectors:* All analytical calculations (repetition, burstiness, syllable counting, Flesch Reading Ease, regex pattern matching, semantic preservation gating, quality score weighting) are custom, bespoke Python routines. No third-party NLP libraries (such as `spaCy`, `nltk`, `textstat`, `vale`, `promptfoo`, or `textlint`) are installed or executed.

---

## 1. Locally Executed Deterministic Components

### 1.1 Markdown Extraction & Masking
- **File & Function:** [`src/md_audit/scanner.py`](file:///C:/Users/matt/ai2human/src/md_audit/scanner.py) — `mask_markdown_prose_detailed(raw_content)` and `scan_directory(root_dir)`.
- **Implementation Type:** Custom bespoke Python code using standard library `re` and `os.walk`.
- **Input Received:** Raw UTF-8 Markdown text string (`raw_content`).
- **Preconditions & Applicability:** File suffix must be `.md` or `.markdown`, and path must not match exclusion patterns (`DEFAULT_EXCLUSIONS` or user exclusions).
- **Rules / Thresholds:**
  - Frontmatter: Detects leading `---` delimiter block and masks lines to empty strings `""`.
  - Code Fences: Detects triple backticks ```` ``` ```` or tildes `~~~` and masks all fenced lines to `""`.
  - HTML Comments: Detects `<!-- ... -->` (single-line or multi-line) and masks to `""`.
  - Inline Code: Replaces backticked spans (e.g. `` `code` ``) with spaces of equal length to preserve column alignment.
  - Links: Replaces image links `![alt](url)` with `alt`, markdown links `[text](url)` with `text`, and autolinks `<url>` with spaces.
- **Output Measurements:**
  - `raw_characters`: Total length of raw document string.
  - `raw_lines`: Line count of raw document.
  - `prose_lines`: Line count of extracted prose (identical length to `raw_lines`).
  - `masked_lines`: Number of lines where raw line differed from masked prose line.
  - `prose_words`: Approximate prose word count via `count_prose_words(prose_lines)`.
  - Counts of masked elements: `frontmatter_lines`, `code_fence_lines`, `html_comment_lines`, `inline_code_spans`, `link_spans`.
- **Conditions Producing Findings:** Does not emit quality findings directly; produces masked input for downstream analysers.
- **Conditions That Skip Analysis:** File not found, permission error, or excluded directory. If document contains 0 prose words, status is marked `not_applicable`.
- **Current Reporting Behaviour:** Exposed in document diagnostics under `markdown_masker`.

---

### 1.2 YAML Rule Loading & Pattern Matching
- **File & Function:** [`src/md_audit/analyzers/deterministic.py`](file:///C:/Users/matt/ai2human/src/md_audit/analyzers/deterministic.py) — `DeterministicAnalyzer.from_rules_directory()` and `DeterministicAnalyzer.analyze()`.
- **Implementation Type:** Custom engine using `PyYAML` for deserialization and standard library `re` for compiled regex matching.
- **Input Received:** `ScannedDocument` containing `prose_lines`.
- **Preconditions & Applicability:** Requires valid YAML rule files in the designated rules directory. If `doc.word_count == 0` or prose is empty, status is `not_applicable`.
- **Rules / Thresholds Configured:**
  - 37 declarative rules loaded across 6 default YAML rule files:
    - `ai_cliches.yaml`: 15 rules (e.g. `ai.cliche.delve`, `ai.cliche.landscape`, `ai.cliche.pivotal_role`, `ai.cliche.leverage`, `ai.cliche.seamless`, `ai.cliche.robust`).
    - `formulaic_structure.yaml`: 8 rules (e.g. `structure.intro.fast_paced`, `structure.closer.formulaic`, `structure.negative_parallelism`).
    - `generic_adjectives.yaml`: 9 rules (e.g. `adj.pivotal`, `adj.comprehensive`, `adj.transformative`, `adj.holistic`).
    - `repetitive_transitions.yaml`: 6 rules (e.g. `transition.moreover`, `transition.furthermore`, `transition.it_is_worth_noting`).
    - `wordy_phrases.yaml`: 9 rules (e.g. `clarity.wordy.in_order_to`, `clarity.wordy.due_to_the_fact`, `clarity.wordy.at_this_point_in_time`).
    - `passive_voice.yaml`: 2 rules (`clarity.passive.was_by`, `clarity.passive.construction`).
  - Multi-line checks:
    - `repetition.sentence_openers`: Sequences of 3+ consecutive sentences starting with the same word.
    - `consistency.terminology`: 6 variant pairs (e.g. `front-end` vs `frontend`, `on-premise` vs `on-premises`, `plugin` vs `plug-in`).
- **Output Measurements:**
  - Match counts per rule (`match_count`).
  - Matched substring (`matched_text`), exact line (`line_number`) and 1-indexed column (`column`).
  - Rules loaded vs failed, rules evaluated vs triggered.
- **Conditions Producing Findings:** Any regex pattern match on non-empty prose lines, 3+ identical sentence openers, or contradictory terminology variants.
- **Conditions That Skip Analysis:** Empty lines, code fences/comments (already masked to empty), or documents with 0 words. Malformed rules in YAML are logged in `rules_failed` and skipped without aborting other rules.
- **Current Reporting Behaviour:** Emits `Finding` instances; summarized in terminal, markdown table, and JSON `yaml_rule_analyzer`.

---

### 1.3 Repetition Analysis
- **File & Function:** [`src/md_audit/analyzers/repetition.py`](file:///C:/Users/matt/ai2human/src/md_audit/analyzers/repetition.py) — `analyze_repetition(doc)`.
- **Implementation Type:** Custom bespoke Python code using `collections.Counter` and regex tokenization.
- **Input Received:** `ScannedDocument` containing `prose_lines` and `prose_content`.
- **Preconditions & Applicability:** Requires at least one non-empty paragraph (`extract_paragraphs`). If 0 paragraphs or 0 words, status is `not_applicable`.
- **Rules / Thresholds Configured:**
  - Transition clustering: Paragraph-opening transitions `{"moreover", "furthermore", "additionally", "consequently", "importantly", "notably"}` with threshold `>= 2` uses across paragraphs.
  - Lexical 3-gram repetition: Case-insensitive trigrams of non-stopwords with threshold `>= 3` occurrences anywhere in document.
- **Output Measurements:**
  - `paragraph_count`: Count of distinct markdown prose paragraphs.
  - `transitions`: Exact count for each transition word.
  - `repeated_phrases`: Top 3-grams with occurrence counts.
  - `sentence_openings`: First word and initial phrase of every paragraph.
- **Conditions Producing Findings:**
  - Transition clustering count `>= 2` -> Warning finding `repetition.transition_clustering`.
  - 3-gram phrase count `>= 3` -> Suggestion finding `repetition.n_gram`.
- **Conditions That Skip Analysis:** Paragraphs starting with markdown formatting (`#`, `-`, `*`, `>`, `|`) are excluded from paragraph transitions. Documents with 0 paragraphs or 0 words are skipped.
- **Current Reporting Behaviour:** Findings attached to document findings; raw metrics captured in `repetition_analyzer` diagnostics.

---

### 1.4 Burstiness & Sentence Variation Analysis
- **File & Function:** [`src/md_audit/analyzers/burstiness.py`](file:///C:/Users/matt/ai2human/src/md_audit/analyzers/burstiness.py) — `analyze_burstiness(doc)`.
- **Implementation Type:** Custom bespoke Python code using standard library `math` and regex sentence segmentation.
- **Input Received:** `ScannedDocument` containing `prose_lines`.
- **Preconditions & Applicability:** Requires at least one sentence extracted via `extract_sentences()`. If 0 sentences, status is `not_applicable`.
- **Rules / Thresholds Configured:**
  - `min_cv: 0.40`: Minimum coefficient of variation (`std_length / mean_length`).
  - `min_sentences: 6`: Minimum sentence sample size required to trigger low-burstiness warning.
- **Output Measurements:**
  - `sentence_count`: Number of extracted prose sentences (length >= 3 words).
  - `mean_length`: Average sentence length in words.
  - `std_length`: Sample standard deviation of sentence lengths (`math.sqrt(variance)` with `n - 1` denominator).
  - `coefficient_of_variation`: Ratio of standard deviation to mean (`std / mean`).
- **Conditions Producing Findings:**
  - If `sentence_count >= 6` and `cv < 0.40` -> Warning finding `readability.low_burstiness`.
- **Conditions That Skip Analysis:** Headers and tables are skipped. Documents with `< 6` sentences evaluate metrics but do not trigger low-burstiness findings. Documents with 0 sentences set status `not_applicable`.
- **Current Reporting Behaviour:** Emits finding if triggered; metrics recorded in `burstiness_analyzer` diagnostics.

---

### 1.5 Readability Calculations
- **File & Function:** [`src/md_audit/analyzers/burstiness.py`](file:///C:/Users/matt/ai2human/src/md_audit/analyzers/burstiness.py) — `analyze_burstiness(doc)` and `count_syllables(word)`.
- **Implementation Type:** Custom bespoke heuristic implementation of the Flesch Reading Ease formula.
- **Input Received:** Extracted sentences from `ScannedDocument`.
- **Preconditions & Applicability:** Requires extracted sentences with words. If 0 sentences, status is `not_applicable`.
- **Rules / Thresholds Configured:**
  - Flesch Reading Ease formula: `206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)`, clamped to `[0.0, 100.0]`.
  - Heuristic syllable counter: Strips trailing non-le `e`, counts contiguous vowel groups `[aeiouy]+`.
  - Dense prose threshold: `flesch_reading_ease < 25.0` AND `mean_sentence_length > 24.0` words AND `sentence_count >= 4`.
- **Output Measurements:**
  - `total_words`: Total word count across extracted sentences.
  - `total_syllables`: Total syllable count estimated by heuristic.
  - `words_per_sentence`: Average words per sentence.
  - `syllables_per_word`: Average syllables per word.
  - `flesch_reading_ease`: Calculated 0-100 Flesch Reading Ease score.
- **Conditions Producing Findings:**
  - If FRE `< 25.0`, avg length `> 24.0` words, and `n >= 4` -> Suggestion finding `readability.dense_prose`.
- **Conditions That Skip Analysis:** If 0 sentences, default FRE 70.0 returned with status `not_applicable`.
- **Current Reporting Behaviour:** Emits finding if triggered; metrics recorded in `readability_analyzer` diagnostics.

---

### 1.6 Quality Scoring
- **File & Function:** [`src/md_audit/scoring.py`](file:///C:/Users/matt/ai2human/src/md_audit/scoring.py) — `QualityScorer.score_document()` and `QualityScorer.aggregate_directory()`.
- **Implementation Type:** Custom explainable scoring model with sublinear power length normalization.
- **Input Received:** `word_count`, list of `Finding` instances, `BurstinessMetrics`, `RepetitionMetrics`.
- **Preconditions & Applicability:** Computes for any scanned document. If `word_count == 0`, status is `not_applicable` with default 100/100.
- **Rules / Thresholds Configured:**
  - Category weights: `ai_patterns: 0.25`, `readability: 0.20`, `repetition: 0.20`, `language_clarity: 0.20`, `consistency: 0.15`.
  - Severity penalties: `error: 12.0`, `warning: 6.0`, `suggestion: 3.0` (unrecognized severity defaults to `4.0`).
  - Scaling denominator: `scaled_denom = max(120, word_count) ** 0.65`.
  - Normalized penalty formula: `normalized_penalty = (raw_penalty / scaled_denom) * 22.0`.
  - Readability penalty adjustment: If `sentence_count >= 5` and `cv < 0.22`, extra `+10.0` penalty added.
  - Category score: `max(0, min(100, int(round(100.0 - total_penalty))))`.
  - Overall score: Weighted sum of category scores rounded to integer.
  - Directory score: Word-count-weighted average across all documents.
- **Output Measurements:**
  - Category scores (0-100), overall score (0-100), rubric explanation string per category.
  - Raw penalties, normalized penalties, special adjustments, weighted contributions, zero-penalty flags.
- **Conditions Producing Findings:** Does not produce findings; converts findings into numerical scores.
- **Conditions That Skip Analysis:** If `word_count == 0`, scores remain 100/100 with status `not_applicable`.
- **Current Reporting Behaviour:** Reported in summary, markdown report, and JSON `quality_scorer` diagnostics.

---

### 1.7 Semantic Preservation Validation
- **File & Function:** [`src/md_audit/validation.py`](file:///C:/Users/matt/ai2human/src/md_audit/validation.py) — `SemanticPreservationGate.validate()`.
- **Implementation Type:** Custom deterministic preservation gate comparing original vs candidate revised text.
- **Input Received:** `original_text: str`, `revised_text: str`.
- **Preconditions & Applicability:** Executed during editorial runs (`improve`, `compare`, or review pipelines). Not invoked during standard read-only directory scanning.
- **Rules / Thresholds Configured:**
  - `strict_code: True`: Fenced code blocks must be byte-for-byte identical in count and content.
  - `strict_numbers: True`: Numerical tokens (integers, floats, percentages, versions, units) must not decrease in frequency or be invented.
  - `strict_dates: True`: Dates and deadlines must not decrease in frequency.
  - `strict_requirements: True`: Uppercase RFC 2119 requirement keywords must not decrease in frequency.
  - `strict_urls: True`: Link targets and raw URLs must not decrease in frequency.
  - `strict_structure: True`: Markdown heading count must match exactly.
  - `strict_inline: True`: Backticked identifiers must not decrease in frequency.
- **Output Measurements:**
  - `is_valid: bool` (`False` if any critical violation detected).
  - `critical_changes_count`, `warning_changes_count`.
  - `checks_run`: List of 7 verification checks with item counts, strict flag, violations detected, and pass/fail status.
  - `material_changes`: List of `MaterialChange` objects with `change_type`, `severity`, `original_value`, `revised_value`, and `explanation`.
- **Conditions Producing Findings:** Any missing number, altered date, dropped code block, modified RFC keyword, missing URL, or changed heading structure.
- **Conditions That Skip Analysis:** Only runs when candidate revisions exist.
- **Current Reporting Behaviour:** Reported in editorial review JSON, comparison summaries, and validation manifests.

---

## 2. Model-Assisted Components (Kept Explicitly Separate)

### 2.1 Model-Assisted Critic
- **File & Function:** [`src/md_audit/analyzers/model_evaluator.py`](file:///C:/Users/matt/ai2human/src/md_audit/analyzers/model_evaluator.py) — `ModelEvaluator.evaluate()`.
- **Implementation Type:** Online LLM via OpenRouter HTTP endpoint (`openai/gpt-4o-mini`) or deterministic local offline simulation.
- **Input Received:** Raw markdown document string, split into section chunks (max 6,000 characters) via `split_markdown_sections()`.
- **Preconditions & Applicability:** Invoked only when `--model-eval` or `--llm` is explicitly requested. Requires `OPENROUTER_API_KEY` unless `--offline` is specified.
- **Output Measurements:**
  - `overall_score`, `naturalness_score`, `clarity_score`, `coherence_score`, `technical_precision_score`.
  - `critique_summary`: Structured prose assessment.
  - `weaknesses`: List of `ModelWeakness` (`aspect`, `quote`, `feedback`).
- **Separation Guarantee:** Model critic scores and findings are stored in a dedicated `model_evaluations` container and are never merged or averaged into local deterministic quality scores.

### 2.2 Contextual Editor & Independent Reviewer
- **File & Function:** [`src/md_audit/editor.py`](file:///C:/Users/matt/ai2human/src/md_audit/editor.py) and [`src/md_audit/llm.py`](file:///C:/Users/matt/ai2human/src/md_audit/llm.py) — `LLMEditor.rewrite_chunk()` and `LLMReviewer.review_chunk()`.
- **Implementation Type:** Online LLMs via OpenRouter (defaults: `deepseek/deepseek-chat` for editor, `qwen/qwen-2.5-72b-instruct` for reviewer) or offline mock.
- **Preconditions & Applicability:** Only invoked during editorial rewriting (`improve` command with `--llm`).
- **Separation Guarantee:** Execution metrics, token usage, and decisions (`Accept`, `Reject`, `Review manually`) are recorded in `editorial-review.json` and are entirely distinct from local static analysis.
