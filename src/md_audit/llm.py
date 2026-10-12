"""LLM contextual rewriting and independent reviewer integration via OpenRouter."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Sequence

import requests


class ModelError(Exception):
    """Raised when an LLM API request fails or credentials are missing."""
    pass


@dataclass
class ReviewResult:
    """Outcome of an independent LLM review pass."""
    decision: str  # "Accept", "Reject", "Review manually", "Unreviewed"
    reason: str
    naturalness_improved: bool
    meaning_changed: bool
    reviewer_model: str
    is_offline: bool = False
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "naturalness_improved": self.naturalness_improved,
            "meaning_changed": self.meaning_changed,
            "reviewer_model": self.reviewer_model,
            "is_offline": self.is_offline,
            "usage": self.usage,
        }


EDITOR_SYSTEM_PROMPTS = {
    "conservative": """You are an expert technical editor. Your job is conservative improvement:
- Make minimal, targeted revisions only to fix obvious writing weaknesses (such as formulaic AI clichés, empty throat-clearing openers, repetitive transitions, or extreme wordiness).
- Do not rewrite good sentences. Retain the author's original structure, voice, and length as closely as possible.
- Never add new facts, change numbers, modify dates, or alter technical requirements.
- Preserve all bracketed token placeholders (such as ⟦FENCED_CODE_BLOCK_0⟧, ⟦INLINE_CODE_0⟧, ⟦LINK_URL_0⟧) exactly as they appear.
- Return ONLY the revised Markdown text without introductory or concluding conversational commentary.
""",
    "balanced": """You are an expert technical editor. Your job is balanced editorial improvement:
- Improve sentence clarity, natural cadence, and flow.
- Remove formulaic AI idioms ("stands as a testament to", "plays a pivotal role", "delve into", "in today's landscape", "unlock potential", "foster collaboration").
- Eliminate unnecessary padding and empty adverbs.
- Convert weak passive phrasing to direct active voice where clear.
- Retain technical precision, tone, and original meaning.
- Never add new facts, change numbers, modify dates, or alter technical requirements.
- Leave well-written, clear passages alone.
- Preserve all bracketed token placeholders (such as ⟦FENCED_CODE_BLOCK_0⟧, ⟦INLINE_CODE_0⟧, ⟦LINK_URL_0⟧) exactly as they appear.
- Return ONLY the revised Markdown text without introductory or concluding conversational commentary.
""",
}

REVIEWER_SYSTEM_PROMPT = """You are an independent editorial quality reviewer. You evaluate proposed revisions to Markdown documents.
Compare the original text and the revised text.
Answer these three questions:
1. Is the revised writing clearer, more concise, and more natural?
2. Has any important meaning, fact, technical requirement, constraint, code identifier, or nuance changed or been lost?
3. Should the proposed revision be accepted?

You must respond with valid JSON matching this schema:
{
  "naturalness_improved": <bool>,
  "meaning_changed": <bool>,
  "decision": "Accept" | "Reject" | "Review manually",
  "reason": "<clear explanation of the verdict>"
}

Strict Rules:
- If ANY technical requirement, constraint, number, or fact was lost or distorted, decision MUST be "Reject".
- If the revision introduces grammatical errors or sounds unnatural, decision should be "Reject" or "Review manually".
- If the revision preserves meaning and improves clarity and naturalness, decision should be "Accept".
"""


def isolate_markdown_elements(text: str) -> tuple[str, list[str], list[str], list[str]]:
    """
    Replace fenced code blocks, inline code, and link URLs with non-colliding tokens
    to prevent LLMs or regex engines from mutating technical tokens.
    """
    code_blocks: list[str] = []
    def save_code_block(match: re.Match) -> str:
        token = f"⟦FENCED_CODE_BLOCK_{len(code_blocks)}⟧"
        code_blocks.append(match.group(0))
        return token

    isolated = re.sub(r"```[a-zA-Z0-9_-]*\n.*?```", save_code_block, text, flags=re.DOTALL)

    inline_codes: list[str] = []
    def save_inline_code(match: re.Match) -> str:
        token = f"⟦INLINE_CODE_{len(inline_codes)}⟧"
        inline_codes.append(match.group(0))
        return token

    isolated = re.sub(r"`[^`\n]+`", save_inline_code, isolated)

    link_urls: list[str] = []
    def save_link_url(match: re.Match) -> str:
        anchor = match.group(1)
        url = match.group(2)
        token = f"⟦LINK_URL_{len(link_urls)}⟧"
        link_urls.append(url)
        return f"[{anchor}]({token})"

    isolated = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", save_link_url, isolated)

    return isolated, code_blocks, inline_codes, link_urls


def restore_markdown_elements(
    isolated_text: str,
    code_blocks: list[str],
    inline_codes: list[str],
    link_urls: list[str],
) -> str:
    """Restore all isolated tokens byte-for-byte."""
    text = isolated_text
    for idx, url in enumerate(link_urls):
        text = text.replace(f"⟦LINK_URL_{idx}⟧", url)
    for idx, code in enumerate(inline_codes):
        text = text.replace(f"⟦INLINE_CODE_{idx}⟧", code)
    for idx, block in enumerate(code_blocks):
        text = text.replace(f"⟦FENCED_CODE_BLOCK_{idx}⟧", block)
    return text


def split_markdown_sections(text: str, max_chars: int = 4000) -> list[str]:
    """
    Split long Markdown documents into sensible sections by heading boundaries (# or ##)
    or paragraph boundaries, avoiding silent truncation on long files while preserving content.
    """
    if len(text) <= max_chars:
        return [text]

    lines = text.splitlines(keepends=True)
    sections: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        is_heading = bool(re.match(r"^#{1,3}\s+", line))
        is_blank = not line.strip()
        line_len = len(line)

        if current_chunk and ((is_heading and current_length >= max_chars) or (is_blank and current_length >= max_chars)):
            sections.append("".join(current_chunk))
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len

    if current_chunk:
        sections.append("".join(current_chunk))

    return sections if sections else [text]


class LLMEditor:
    """Performs contextual LLM rewriting of Markdown documents via OpenRouter."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "deepseek/deepseek-chat",
        api_key: str | None = None,
        offline_mode: bool = False,
        timeout: int = 45,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.offline_mode = offline_mode
        self.timeout = timeout
        self.last_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def rewrite(self, text: str, mode: str = "balanced") -> str:
        """
        Rewrite document with LLM. Splits long documents into sections,
        isolates code blocks/links, and reassembles output.
        """
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        mode = mode.lower() if mode in EDITOR_SYSTEM_PROMPTS else "balanced"

        if self.offline_mode:
            return self._rewrite_offline(text, mode=mode)

        if not self.api_key:
            raise ModelError(
                "OPENROUTER_API_KEY is not set. Set the environment variable OPENROUTER_API_KEY "
                "or run with --offline for local simulation."
            )

        # 1. Isolate code blocks, inline code, and URLs
        isolated, code_blocks, inline_codes, link_urls = isolate_markdown_elements(text)

        # 2. Split into sensible sections if large
        sections = split_markdown_sections(isolated, max_chars=4500)
        rewritten_sections: list[str] = []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/matthew-thomasson/human2ai",
            "X-Title": "Markdown Quality Auditor",
        }

        system_prompt = EDITOR_SYSTEM_PROMPTS[mode]

        for sec in sections:
            # Skip empty or whitespace-only sections
            if not sec.strip():
                rewritten_sections.append(sec)
                continue

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Please edit this Markdown section for naturalness, clarity, and flow. "
                            "Preserve all tokens like ⟦...⟧ exactly:\n\n" + sec
                        ),
                    },
                ],
                "temperature": 0.2 if mode == "conservative" else 0.4,
            }

            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    raise ModelError(
                        f"OpenRouter API error (HTTP {resp.status_code}): {resp.text}"
                    )
                data = resp.json()
                usage = data.get("usage", {})
                if isinstance(usage, dict):
                    self.last_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    self.last_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                    self.last_usage["total_tokens"] += usage.get("total_tokens", 0)

                sec_out = data["choices"][0]["message"]["content"]
                # Strip any accidental wrapping ```markdown code fences emitted by the model
                sec_out = re.sub(r"^```markdown\s*\n", "", sec_out, flags=re.IGNORECASE)
                sec_out = re.sub(r"\n```\s*$", "", sec_out)
                rewritten_sections.append(sec_out)
            except requests.RequestException as e:
                raise ModelError(f"Network error connecting to OpenRouter: {e}") from e
            except (KeyError, IndexError) as e:
                raise ModelError(f"Unexpected response format from model {self.model}: {e}") from e

        combined = "\n".join(rewritten_sections)
        # 3. Restore all isolated tokens
        final_text = restore_markdown_elements(combined, code_blocks, inline_codes, link_urls)
        return final_text

    def _rewrite_offline(self, text: str, mode: str = "balanced") -> str:
        """Deterministic offline mock editor for local test execution."""
        from .editor import strip_leading_openers, apply_safe_replacements

        # Apply safe substitutions
        revised, _ = strip_leading_openers(text)
        revised, _ = apply_safe_replacements(revised)

        # In balanced mode, also smooth passive phrases
        if mode == "balanced":
            revised = re.sub(r"\butilize automated pipelines\b", "use automated pipelines", revised, flags=re.I)
            revised = re.sub(r"\bis indicative of cloud maturity\b", "reflects cloud maturity", revised, flags=re.I)

        return revised


class LLMReviewer:
    """Assesses proposed revisions using an independent OpenRouter model."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "qwen/qwen-2.5-72b-instruct",
        api_key: str | None = None,
        offline_mode: bool = False,
        timeout: int = 45,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.offline_mode = offline_mode
        self.timeout = timeout

    def review(self, original: str, revised: str) -> ReviewResult:
        """Review proposed edit and return Accept, Reject, or Review manually."""
        if self.offline_mode:
            return self._review_offline(original, revised)

        if not self.api_key:
            return ReviewResult(
                decision="Unreviewed",
                reason="Reviewer skipped: OPENROUTER_API_KEY is not set.",
                naturalness_improved=False,
                meaning_changed=False,
                reviewer_model=self.model,
                is_offline=False,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/matthew-thomasson/human2ai",
            "X-Title": "Markdown Quality Auditor",
        }

        user_content = (
            f"### ORIGINAL TEXT:\n{original[:4000]}\n\n"
            f"### REVISED TEXT:\n{revised[:4000]}\n\n"
            "Evaluate whether the revision should be accepted."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return ReviewResult(
                    decision="Unreviewed",
                    reason=f"Reviewer unavailable (HTTP {resp.status_code}): {resp.text[:120]}",
                    naturalness_improved=False,
                    meaning_changed=False,
                    reviewer_model=self.model,
                    is_offline=False,
                )

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            usage = data.get("usage", {})
            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0,
                "completion_tokens": usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0,
                "total_tokens": usage.get("total_tokens", 0) if isinstance(usage, dict) else 0,
            }

            dec = parsed.get("decision", "Review manually")
            if dec not in {"Accept", "Reject", "Review manually"}:
                dec = "Review manually"

            return ReviewResult(
                decision=dec,
                reason=parsed.get("reason", "Review completed."),
                naturalness_improved=bool(parsed.get("naturalness_improved", True)),
                meaning_changed=bool(parsed.get("meaning_changed", False)),
                reviewer_model=self.model,
                is_offline=False,
                usage=usage_dict,
            )
        except Exception as e:
            # When reviewer is unavailable, flag as unreviewed rather than pretending it passed
            return ReviewResult(
                decision="Unreviewed",
                reason=f"Reviewer unavailable: {e}",
                naturalness_improved=False,
                meaning_changed=False,
                reviewer_model=self.model,
                is_offline=False,
            )

    def _review_offline(self, original: str, revised: str) -> ReviewResult:
        """Deterministic offline mock reviewer for tests."""
        # Check if text is identical
        if original.strip() == revised.strip():
            return ReviewResult(
                decision="Accept",
                reason="No changes were necessary; text is already clean.",
                naturalness_improved=True,
                meaning_changed=False,
                reviewer_model=f"{self.model} (offline-simulation)",
                is_offline=True,
            )

        # Heuristic checks: if numbers changed or RFC keywords weakened, reject
        from .validation import SemanticPreservationGate
        val = SemanticPreservationGate().validate(original, revised)
        if not val.is_valid:
            crit = [c.explanation for c in val.material_changes if c.severity == "critical"]
            return ReviewResult(
                decision="Reject",
                reason=f"Protected elements altered: {'; '.join(crit)}",
                naturalness_improved=False,
                meaning_changed=True,
                reviewer_model=f"{self.model} (offline-simulation)",
                is_offline=True,
            )

        return ReviewResult(
            decision="Accept",
            reason="Revision improves naturalness while strictly preserving factual meaning.",
            naturalness_improved=True,
            meaning_changed=False,
            reviewer_model=f"{self.model} (offline-simulation)",
            is_offline=True,
        )
