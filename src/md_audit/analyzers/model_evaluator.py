"""Model-assisted writing quality critic and AI-style evaluator (OpenRouter / OpenAI compatible)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from ..llm import ModelError, split_markdown_sections
from ..scanner import ScannedDocument


@dataclass
class ModelWeakness:
    """Specific weakness identified by the model critic."""
    aspect: str
    quote: str
    feedback: str


@dataclass
class ModelAIStyleObservation:
    """Individual observation from independent model-assisted AI-style evaluation."""
    category: str  # formulaic_phrasing, repetitive_reasoning, generic_statements, uniform_organisation, weakly_supported_assertions, passages_warranting_review
    quote: str
    source_reference: str
    observation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "quote": self.quote,
            "source_reference": self.source_reference,
            "observation": self.observation,
        }


@dataclass
class ModelAIStyleAssessment:
    """Structured AI-style evaluation output from the independent model critic (Enhancement D)."""
    file_path: str
    model_identifier: str
    execution_status: str  # "completed", "offline_simulated", "failed"
    token_usage: dict[str, int]
    estimated_cost_usd: float
    disclaimer: str
    observations: list[ModelAIStyleObservation]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        categories = [
            "formulaic_phrasing",
            "repetitive_reasoning",
            "generic_statements",
            "uniform_organisation",
            "weakly_supported_assertions",
            "passages_warranting_review",
        ]
        return {
            "file": self.file_path,
            "model": self.model_identifier,
            "execution_status": self.execution_status,
            "token_usage": self.token_usage,
            "estimated_cost_usd": self.estimated_cost_usd,
            "disclaimer": self.disclaimer,
            "summary": self.summary,
            "observations_count": len(self.observations),
            "observations": [o.to_dict() for o in self.observations],
            "observations_by_category": {
                cat: [o.to_dict() for o in self.observations if o.category == cat]
                for cat in categories
            },
        }


@dataclass
class ModelEvaluationResult:
    """Structured evaluation output from the model-assisted critic."""
    file_path: str
    overall_score: int  # 0 to 100
    naturalness_score: int
    clarity_score: int
    coherence_score: int
    technical_precision_score: int
    critique_summary: str
    weaknesses: list[ModelWeakness]
    is_offline: bool
    model_identifier: str
    ai_style_assessment: ModelAIStyleAssessment | None = None
    token_usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "file": self.file_path,
            "overall_score": self.overall_score,
            "naturalness_score": self.naturalness_score,
            "clarity_score": self.clarity_score,
            "coherence_score": self.coherence_score,
            "technical_precision_score": self.technical_precision_score,
            "critique_summary": self.critique_summary,
            "weaknesses": [
                {"aspect": w.aspect, "quote": w.quote, "feedback": w.feedback}
                for w in self.weaknesses
            ],
            "is_offline": self.is_offline,
            "model": self.model_identifier,
            "token_usage": self.token_usage,
            "estimated_cost_usd": self.estimated_cost_usd,
        }
        if self.ai_style_assessment:
            d["ai_style_assessment"] = self.ai_style_assessment.to_dict()
        return d


CRITIC_SYSTEM_PROMPT = """You are an expert editorial critic evaluating Markdown documentation.
Evaluate the supplied Markdown text strictly on these dimensions:
1. Naturalness: Does it read like human expert prose or synthetic AI text?
2. Audience appropriateness & purpose: Does it directly serve the reader without empty padding?
3. Logical coherence: Are paragraphs reasoned and well-structured?
4. Repetition & redundancy: Are ideas, transitions, or phrases repeated unnecessarily?
5. Technical precision & unsubstantiated claims: Are assertions specific and verifiable?

Do NOT rewrite the text. Act only as an independent critic.
You must respond with valid JSON matching this schema:
{
  "naturalness_score": <int 0-100>,
  "clarity_score": <int 0-100>,
  "coherence_score": <int 0-100>,
  "technical_precision_score": <int 0-100>,
  "overall_model_score": <int 0-100>,
  "critique_summary": "<concise summary>",
  "identified_weaknesses": [
    {"aspect": "<aspect name>", "quote": "<exact quote from text>", "feedback": "<editorial advice>"}
  ]
}
"""

AI_STYLE_SYSTEM_PROMPT = """You are an independent editorial critic analyzing stylistic and structural characteristics in Markdown prose.
Your goal is to evaluate formulaic, repetitive, and generic writing characteristics with academic rigor.

CRITICAL INSTRUCTIONS & GUARDRAILS:
1. Writing style CANNOT reliably establish authorship.
2. Human writing can exhibit AI-associated patterns (e.g. templates, formulaic student essays, corporate memos).
3. AI-generated writing can appear natural, varied, and idiosyncratic.
4. An unfinished student template or outline MUST NOT be assessed as a finished essay; evaluate it in its proper genre context.
5. You MUST NOT infer, compute, or state an AI-authorship percentage or probability.
6. For every observation, you MUST provide an exact verbatim quotation from the text.

Identify specific instances in these categories:
- formulaic_phrasing: Overused idioms, stock transitions, significance puffery ("delve into", "plays a pivotal role", "landscape", "testament").
- repetitive_reasoning: Restating the same underlying idea or argument across paragraphs with superficial lexical variation.
- generic_statements: High-level unanchored claims lacking concrete domain facts, specific examples, numbers, or citations.
- uniform_organisation: Rigid, unnaturally repetitive paragraph structures or predictable rhythmic cadence.
- weakly_supported_assertions: Broad claims presented as facts without justification or supporting data.
- passages_warranting_review: Specific sections that would benefit from human editorial attention.

You must respond with valid JSON matching this schema:
{
  "summary": "<concise evidence-based assessment summary without authorship claims>",
  "observations": [
    {
      "category": "<one of: formulaic_phrasing, repetitive_reasoning, generic_statements, uniform_organisation, weakly_supported_assertions, passages_warranting_review>",
      "quote": "<exact verbatim quote from the text>",
      "source_reference": "<section title or approximate line>",
      "observation": "<specific editorial note explaining why this reflects formulaic/generic style>"
    }
  ]
}
"""

AI_STYLE_DISCLAIMER = (
    "Model-assisted evaluations reflect LLM editorial observations and heuristics. "
    "They do NOT provide proof of machine authorship or human authorship. "
    "All observations are presented as editorial critiques with exact source quotations."
)


class ModelEvaluator:
    """Invokes LLM critic (via OpenRouter or compatible provider) or runs offline evaluation."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        offline_mode: bool = False,
        timeout: int = 45,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.offline_mode = offline_mode
        self.timeout = timeout

    def evaluate(self, doc: ScannedDocument) -> ModelEvaluationResult:
        """
        Evaluate a complete document using the model critic or offline heuristic evaluator.
        Reuses heading-based chunking to support long documents without truncation.
        """
        chunks = split_markdown_sections(doc.raw_content, max_chars=6000)

        if self.offline_mode:
            chunk_results = [
                self._evaluate_chunk_offline(chunk, doc.path, idx, len(chunks))
                for idx, chunk in enumerate(chunks, 1)
            ]
            res = self._combine_evaluations(
                doc.path, chunk_results, f"{self.model} (offline-simulation)", is_offline=True
            )
            res.ai_style_assessment = self.evaluate_ai_style(doc)
            return res

        res = self._evaluate_online(doc, chunks)
        try:
            res.ai_style_assessment = self.evaluate_ai_style(doc)
        except Exception:
            # Fall back to offline AI-style assessment if online call encounters error
            res.ai_style_assessment = self._evaluate_ai_style_offline(doc)
        return res

    def evaluate_ai_style(self, doc: ScannedDocument) -> ModelAIStyleAssessment:
        """
        Perform independent model-assisted AI-style assessment (Enhancement D).
        Uses strict non-authorship guardrails and direct quote requirements.
        """
        if self.offline_mode or not self.api_key:
            return self._evaluate_ai_style_offline(doc)

        return self._evaluate_ai_style_online(doc)

    def _evaluate_online(self, doc: ScannedDocument, chunks: list[str]) -> ModelEvaluationResult:
        if not self.api_key:
            raise ModelError(
                "OPENROUTER_API_KEY is not set. Set the environment variable OPENROUTER_API_KEY "
                "or pass --offline for local simulation."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/matthew-thomasson/human2ai",
            "X-Title": "Markdown Quality Auditor",
        }

        chunk_results: list[ModelEvaluationResult] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for idx, chunk in enumerate(chunks, 1):
            sec_header = f" (Section {idx}/{len(chunks)})" if len(chunks) > 1 else ""
            user_content = f"Please evaluate this Markdown document{sec_header}:\n\n{chunk}"

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }

            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    raise ModelError(f"OpenRouter API error (HTTP {resp.status_code}): {resp.text}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                usage = data.get("usage", {})
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)

                weaknesses = [
                    ModelWeakness(
                        aspect=w.get("aspect", "general"),
                        quote=w.get("quote", ""),
                        feedback=w.get("feedback", ""),
                    )
                    for w in parsed.get("identified_weaknesses", [])
                ]

                chunk_results.append(
                    ModelEvaluationResult(
                        file_path=doc.path,
                        overall_score=int(parsed.get("overall_model_score", 75)),
                        naturalness_score=int(parsed.get("naturalness_score", 75)),
                        clarity_score=int(parsed.get("clarity_score", 75)),
                        coherence_score=int(parsed.get("coherence_score", 75)),
                        technical_precision_score=int(parsed.get("technical_precision_score", 75)),
                        critique_summary=parsed.get("critique_summary", "Evaluation complete."),
                        weaknesses=weaknesses,
                        is_offline=False,
                        model_identifier=self.model,
                    )
                )
            except requests.RequestException as e:
                raise ModelError(f"Network error connecting to OpenRouter: {e}") from e
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                raise ModelError(f"Unexpected response format from model {self.model}: {e}") from e

        combined = self._combine_evaluations(doc.path, chunk_results, self.model, is_offline=False)
        total_tokens = total_prompt_tokens + total_completion_tokens
        cost = (total_prompt_tokens * 0.15 + total_completion_tokens * 0.60) / 1_000_000.0
        combined.token_usage = {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        }
        combined.estimated_cost_usd = round(cost, 6)
        return combined

    def _evaluate_ai_style_online(self, doc: ScannedDocument) -> ModelAIStyleAssessment:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/matthew-thomasson/human2ai",
            "X-Title": "Markdown Quality Auditor",
        }

        # Truncate content to 8000 characters if very long to stay well within single-call context
        content_sample = doc.raw_content[:8000]
        user_content = (
            f"Please conduct an independent AI-style and structural assessment of this document:\n\n{content_sample}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": AI_STYLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return self._evaluate_ai_style_offline(doc)

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            usage = data.get("usage", {})
            p_tok = usage.get("prompt_tokens", 0)
            c_tok = usage.get("completion_tokens", 0)
            cost = (p_tok * 0.15 + c_tok * 0.60) / 1_000_000.0

            obs_list = [
                ModelAIStyleObservation(
                    category=obs.get("category", "formulaic_phrasing"),
                    quote=obs.get("quote", ""),
                    source_reference=obs.get("source_reference", "General"),
                    observation=obs.get("observation", ""),
                )
                for obs in parsed.get("observations", [])
            ]

            return ModelAIStyleAssessment(
                file_path=doc.path,
                model_identifier=self.model,
                execution_status="completed",
                token_usage={"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": p_tok + c_tok},
                estimated_cost_usd=round(cost, 6),
                disclaimer=AI_STYLE_DISCLAIMER,
                observations=obs_list,
                summary=parsed.get("summary", "Model-assisted AI-style assessment completed."),
            )
        except Exception:
            return self._evaluate_ai_style_offline(doc)

    def _evaluate_ai_style_offline(self, doc: ScannedDocument) -> ModelAIStyleAssessment:
        """Deterministic offline simulated AI-style evaluation with authentic quotes."""
        content = doc.raw_content
        obs: list[ModelAIStyleObservation] = []

        # Check for bracketed template instructions
        bracket_matches = re.findall(r"\[(Explain|Describe|Evaluate|Analyse|Identify)[^\]]{5,80}\]", content)
        if bracket_matches:
            obs.append(
                ModelAIStyleObservation(
                    category="uniform_organisation",
                    quote=f"[{bracket_matches[0]}]",
                    source_reference="Instructional Scaffolding",
                    observation="Document contains bracketed prompt templates indicating an instructional scaffold or template structure rather than a finished essay.",
                )
            )

        # Check for formulaic clichés
        if "in today's" in content.lower():
            obs.append(
                ModelAIStyleObservation(
                    category="formulaic_phrasing",
                    quote="in today's ...",
                    source_reference="Introductory passage",
                    observation="Employs conventional opening phrase common to synthetic introductory paragraphs.",
                )
            )

        if "pivotal role" in content.lower():
            obs.append(
                ModelAIStyleObservation(
                    category="formulaic_phrasing",
                    quote="pivotal role",
                    source_reference="Body text",
                    observation="Uses overused significance adjective without concrete contribution details.",
                )
            )

        if "holistic" in content.lower() or "synergy" in content.lower():
            obs.append(
                ModelAIStyleObservation(
                    category="generic_statements",
                    quote="holistic / synergy",
                    source_reference="Body text",
                    observation="Employs abstract corporate buzzwords lacking specific empirical anchoring.",
                )
            )

        summary = (
            f"Offline simulated evaluation completed. Identified {len(obs)} stylistic observations. "
            "Note: Patterns reflect formulaic structure and scaffolding, not authorship origin."
        )

        return ModelAIStyleAssessment(
            file_path=doc.path,
            model_identifier=f"{self.model} (offline-simulation)",
            execution_status="offline_simulated",
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            estimated_cost_usd=0.0,
            disclaimer=AI_STYLE_DISCLAIMER,
            observations=obs,
            summary=summary,
        )

    def _evaluate_chunk_offline(
        self, chunk: str, file_path: str, chunk_index: int = 1, total_chunks: int = 1
    ) -> ModelEvaluationResult:
        """Deterministic offline evaluation of a single document chunk."""
        content = chunk.lower()
        weaknesses: list[ModelWeakness] = []
        score = 85

        # Heuristic checks mirroring prompt criteria
        if "in today's" in content or "digital age" in content:
            score -= 15
            weaknesses.append(
                ModelWeakness(
                    aspect="Generic tone",
                    quote="in today's ...",
                    feedback="Document opens with generic introductory platitudes instead of immediate purpose.",
                )
            )

        if "stands as a testament" in content or "pivotal role" in content:
            score -= 10
            weaknesses.append(
                ModelWeakness(
                    aspect="Unsubstantiated claims",
                    quote="stands as a testament / pivotal role",
                    feedback="Uses hyperbole and ungrounded significance adjectives without supporting metrics.",
                )
            )

        if "it's not just" in content or "not about" in content:
            score -= 10
            weaknesses.append(
                ModelWeakness(
                    aspect="Formulaic structure",
                    quote="it's not ..., it's ...",
                    feedback="Contains synthetic negative parallelism common in generative outputs.",
                )
            )

        score = max(35, min(98, score))
        summary = "Offline simulated evaluation based on structural and rhetorical analysis."
        if total_chunks > 1:
            summary = f"Section {chunk_index}/{total_chunks}: {summary}"

        return ModelEvaluationResult(
            file_path=file_path,
            overall_score=score,
            naturalness_score=score,
            clarity_score=min(100, score + 5),
            coherence_score=min(100, score + 4),
            technical_precision_score=score,
            critique_summary=summary,
            weaknesses=weaknesses,
            is_offline=True,
            model_identifier=f"{self.model} (offline-simulation)",
        )

    def _combine_evaluations(
        self,
        file_path: str,
        chunk_results: list[ModelEvaluationResult],
        model_identifier: str,
        is_offline: bool,
    ) -> ModelEvaluationResult:
        """Combine section-level evaluations into a unified document-level result."""
        if not chunk_results:
            return ModelEvaluationResult(
                file_path=file_path,
                overall_score=75,
                naturalness_score=75,
                clarity_score=75,
                coherence_score=75,
                technical_precision_score=75,
                critique_summary="No content evaluated.",
                weaknesses=[],
                is_offline=is_offline,
                model_identifier=model_identifier,
            )

        if len(chunk_results) == 1:
            return chunk_results[0]

        n = len(chunk_results)
        avg_overall = round(sum(r.overall_score for r in chunk_results) / n)
        avg_nat = round(sum(r.naturalness_score for r in chunk_results) / n)
        avg_clarity = round(sum(r.clarity_score for r in chunk_results) / n)
        avg_coherence = round(sum(r.coherence_score for r in chunk_results) / n)
        avg_prec = round(sum(r.technical_precision_score for r in chunk_results) / n)

        all_weaknesses: list[ModelWeakness] = []
        summary_lines = [f"Complete document evaluated across {n} sections:"]
        for idx, r in enumerate(chunk_results, 1):
            summary_lines.append(f"- Section {idx}: {r.critique_summary}")
            all_weaknesses.extend(r.weaknesses)

        return ModelEvaluationResult(
            file_path=file_path,
            overall_score=avg_overall,
            naturalness_score=avg_nat,
            clarity_score=avg_clarity,
            coherence_score=avg_coherence,
            technical_precision_score=avg_prec,
            critique_summary="\n".join(summary_lines),
            weaknesses=all_weaknesses,
            is_offline=is_offline,
            model_identifier=model_identifier,
        )
