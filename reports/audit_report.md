# Markdown Quality Audit Report

**Directory:** `fixtures`  
**Timestamp:** `2026-10-12T16:21:16.974420+00:00`  
**Tool Version:** `md-audit v0.1.0`  
**Ruleset Version:** `1.0.0`  

> [!NOTE]
> Scores reflect writing quality, stylistic clarity, and natural cadence. They do NOT represent an AI-authorship probability or detector verdict.

## Executive Summary

- **Files analysed:** 5
- **Total word count:** 528
- **Overall writing quality:** **89/100**
- **Files with improvement opportunities:** 4

### Category Scores

| Category | Score | Weight |
|---|---:|---:|
| AI-style patterns | 73/100 | 25% |
| Readability | 95/100 | 20% |
| Repetition | 94/100 | 20% |
| Language clarity | 88/100 | 20% |
| Consistency | 100/100 | 15% |

## File-by-File Breakdown

### `ai_technical.md`
- **Quality Score:** 74/100
- **Words:** 153
- **Total Findings:** 22

| Line | Severity | Rule ID | Matched Text | Explanation & Suggestion |
|---:|---|---|---|---|
| 1 | `warning` | `readability.low_burstiness` | `Sentence CV: 0.28 (std: 3.6, mean: 12.6)` | Overly uniform sentence structures (burstiness CV: 0.28 < 0.40). Sentences are all roughly the same length, a common fingerprint of machine-generated text. **Suggestion:** Vary your rhythm: mix short punchy sentences (3-7 words) with occasional complex sentences. |
| 3 | `warning` | `ai.cliche.testament` | `stand as a testament to` | 'stands as a testament to' is formulaic significance puffery. **Suggestion:** State the concrete achievement or evidence directly. |
| 5 | `suggestion` | `adj.crucial` | `crucial` | 'crucial' is heavily overused by LLMs to create artificial importance. **Suggestion:** Use 'important', 'necessary', or cut entirely. |
| 5 | `warning` | `ai.cliche.delve` | `delve into` | 'delve into' is a classic AI-style cliché. **Suggestion:** Use 'examine', 'explore', 'look at', or state the topic directly. |
| 5 | `warning` | `ai.cliche.pivotal_role` | `play a pivotal role` | 'plays a pivotal/crucial role' is vague puffery. **Suggestion:** Explain what it actually does or how it contributes. |
| 5 | `warning` | `adj.pivotal` | `a pivotal` | 'pivotal' is an overused hyperbole for standard components or steps. **Suggestion:** Use 'key', 'main', or describe why it matters. |
| 5 | `warning` | `ai.cliche.unlock_potential` | `unlocking the full potential` | 'unlock potential' is marketing cliché. **Suggestion:** State the actual benefit, feature, or metric. |
| 5 | `warning` | `ai.cliche.foster_collaboration` | `foster seamless collaboration` | 'foster collaboration' is abstract filler. **Suggestion:** Use 'help teams work together', 'coordinate', or describe the workflow. |
| 5 | `warning` | `ai.cliche.seamless` | `seamless` | 'seamless' is an overused promise that masks technical complexity. **Suggestion:** Describe the actual user experience or integration mechanism. |
| 7 | `error` | `structure.negative_parallelism` | `It's not just a technical deployment, it's` | Negative parallelism ('It's not X, it's Y' / 'This isn't about X, it's about Y') is a prominent AI rhetorical pattern. **Suggestion:** State the positive claim directly without negating an objection nobody raised. |
| 7 | `warning` | `ai.cliche.groundbreaking` | `groundbreaking` | 'groundbreaking' is unsupported self-praise. **Suggestion:** State what is new or what prior limitation was solved. |
| 7 | `suggestion` | `clarity.wordy.is_indicative_of` | `is indicative of` | 'is indicative of' is weak passive nominalization. **Suggestion:** Use 'indicates' or 'shows'. |
| 7 | `suggestion` | `ai.cliche.utilize` | `utilize` | 'utilize' is needlessly formal when 'use' suffices. **Suggestion:** Use 'use'. |
| 7 | `suggestion` | `clarity.wordy.in_order_to` | `in order to` | 'in order to' is wordy filler. **Suggestion:** Use 'to'. |
| 7 | `warning` | `clarity.wordy.due_to_the_fact` | `due to the fact that` | 'due to the fact that' is unnecessarily verbose. **Suggestion:** Use 'because'. |
| 9 | `warning` | `transition.moreover` | `Moreover,` | 'Moreover' is an overused connective that flags stiff, academic or AI-generated prose. **Suggestion:** Omit or let the sentence stand on its own without a connective adverb. |
| 9 | `warning` | `ai.cliche.tapestry` | `rich tapestry of` | 'tapestry of' is ornate, generic AI imagery. **Suggestion:** Use 'mix of', 'range of', or name the specific components. |
| 9 | `warning` | `transition.it_is_worth_noting` | `It is worth noting that` | 'It is worth noting that' is empty hedge filler. **Suggestion:** Delete the phrase and state the note directly. |
| 9 | `warning` | `clarity.wordy.at_this_point_in_time` | `at this point in time` | 'at this point in time' is wordy padding. **Suggestion:** Use 'now' or 'currently'. |
| 11 | `error` | `structure.closer.formulaic` | `In conclusion` | Formulaic essay conclusion marker. **Suggestion:** Omit the transition word. End on a concrete recommendation or next step. |
| 11 | `warning` | `structure.closer.bright_future` | `the future looks bright` | Clichéd platitude concluding sentence. **Suggestion:** Conclude with specific facts, milestones, or deliverables. |
| 11 | `warning` | `structure.closer.bright_future` | `Only time will tell` | Clichéd platitude concluding sentence. **Suggestion:** Conclude with specific facts, milestones, or deliverables. |

### `good_technical.md`
- **Quality Score:** 100/100
- **Words:** 119
- **Total Findings:** 0

*No issues identified in this file.*

### `markdown_features.md`
- **Quality Score:** 99/100
- **Words:** 61
- **Total Findings:** 1

| Line | Severity | Rule ID | Matched Text | Explanation & Suggestion |
|---:|---|---|---|---|
| 5 | `suggestion` | `adj.comprehensive` | `comprehensive` | 'comprehensive' is frequently used as generic filler. **Suggestion:** Use 'complete', 'detailed', or omit. |

### `numerical_requirements.md`
- **Quality Score:** 97/100
- **Words:** 95
- **Total Findings:** 1

| Line | Severity | Rule ID | Matched Text | Explanation & Suggestion |
|---:|---|---|---|---|
| 1 | `warning` | `readability.low_burstiness` | `Sentence CV: 0.19 (std: 1.8, mean: 9.1)` | Overly uniform sentence structures (burstiness CV: 0.19 < 0.40). Sentences are all roughly the same length, a common fingerprint of machine-generated text. **Suggestion:** Vary your rhythm: mix short punchy sentences (3-7 words) with occasional complex sentences. |

### `repetitive_marketing.md`
- **Quality Score:** 83/100
- **Words:** 100
- **Total Findings:** 14

| Line | Severity | Rule ID | Matched Text | Explanation & Suggestion |
|---:|---|---|---|---|
| 1 | `warning` | `readability.low_burstiness` | `Sentence CV: 0.23 (std: 1.9, mean: 8.0)` | Overly uniform sentence structures (burstiness CV: 0.23 < 0.40). Sentences are all roughly the same length, a common fingerprint of machine-generated text. **Suggestion:** Vary your rhythm: mix short punchy sentences (3-7 words) with occasional complex sentences. |
| 3 | `warning` | `repetition.sentence_openers` | `'The' repeated 3 times` | Three consecutive sentences begin with the same word ('the'). **Suggestion:** Vary your sentence openings to create natural prose cadence. |
| 3 | `warning` | `ai.cliche.seamless` | `seamless` | 'seamless' is an overused promise that masks technical complexity. **Suggestion:** Describe the actual user experience or integration mechanism. |
| 5 | `suggestion` | `adj.innovative` | `innovative` | 'innovative' is generic self-praise without technical substance. **Suggestion:** Explain the novelty or technical mechanism directly. |
| 5 | `suggestion` | `adj.comprehensive` | `comprehensive` | 'comprehensive' is frequently used as generic filler. **Suggestion:** Use 'complete', 'detailed', or omit. |
| 5 | `warning` | `adj.transformative` | `transformative` | 'transformative' is inflated marketing prose. **Suggestion:** State the concrete change or measurable outcome. |
| 5 | `warning` | `adj.holistic` | `holistic` | 'holistic' is a buzzword that often adds no specific meaning. **Suggestion:** Use 'complete', 'end-to-end', or 'whole'. |
| 5 | `warning` | `ai.cliche.harness` | `harness the power of` | 'harness the power of' is dramatic cliché. **Suggestion:** Use 'use' or state the integration plainly. |
| 7 | `warning` | `transition.moreover` | `Moreover,` | 'Moreover' is an overused connective that flags stiff, academic or AI-generated prose. **Suggestion:** Omit or let the sentence stand on its own without a connective adverb. |
| 7 | `warning` | `ai.cliche.groundbreaking` | `groundbreaking` | 'groundbreaking' is unsupported self-praise. **Suggestion:** State what is new or what prior limitation was solved. |
| 7 | `warning` | `adj.vibrant` | `vibrant` | 'vibrant' is decorative filler common in AI travel and culture prose. **Suggestion:** Describe the specific activity, community, or setting. |
| 7 | `warning` | `ai.cliche.leverage` | `leverage` | 'leverage' as a verb is corporate AI-speak. **Suggestion:** Use 'use', 'apply', or 'build upon'. |
| 7 | `warning` | `ai.cliche.beacon` | `beacon of` | 'beacon of' is rhetorical hyperbole. **Suggestion:** State the fact or role without figurative embellishment. |
| 9 | `warning` | `repetition.sentence_openers` | `'The' repeated 3 times` | Three consecutive sentences begin with the same word ('the'). **Suggestion:** Vary your sentence openings to create natural prose cadence. |
