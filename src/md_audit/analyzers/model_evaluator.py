"""Model-assisted writing quality critic (OpenRouter / OpenAI compatible)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
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

    def to_dict(self) -> dict:
        return {
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
        }


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


class ModelEvaluator:
    """Invokes LLM critic (via OpenRouter or compatible provider) or runs offline evaluation."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        offline_mode: bool = False,
        timeout: int = 30,
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
            return self._combine_evaluations(
                doc.path, chunk_results, f"{self.model} (offline-simulation)", is_offline=True
            )

        return self._evaluate_online(doc, chunks)

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

        return self._combine_evaluations(doc.path, chunk_results, self.model, is_offline=False)

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
