"""Model-assisted writing quality critic (OpenRouter / OpenAI compatible)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from ..llm import ModelError
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
        """Evaluate a document using the model critic or offline heuristic evaluator."""
        if self.offline_mode:
            return self._evaluate_offline(doc)

        return self._evaluate_online(doc)

    def _evaluate_online(self, doc: ScannedDocument) -> ModelEvaluationResult:
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

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": f"Please evaluate this Markdown document:\n\n{doc.raw_content[:8000]}"},
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

            return ModelEvaluationResult(
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
        except requests.RequestException as e:
            raise ModelError(f"Network error connecting to OpenRouter: {e}") from e
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ModelError(f"Unexpected response format from model {self.model}: {e}") from e

    def _evaluate_offline(self, doc: ScannedDocument) -> ModelEvaluationResult:
        """Deterministic offline mock / heuristic critic for repeatable local runs and testing."""
        content = doc.prose_content.lower()

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

        return ModelEvaluationResult(
            file_path=doc.path,
            overall_score=score,
            naturalness_score=score,
            clarity_score=min(100, score + 5),
            coherence_score=min(100, score + 4),
            technical_precision_score=score,
            critique_summary="Offline simulated evaluation based on structural and rhetorical analysis.",
            weaknesses=weaknesses,
            is_offline=True,
            model_identifier=f"{self.model} (offline-simulation)",
        )
