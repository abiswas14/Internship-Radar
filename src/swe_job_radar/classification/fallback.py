from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from swe_job_radar.models import Classification, ClassificationResult, Job


class AmbiguousClassificationFallback(Protocol):
    async def classify(self, job: Job) -> ClassificationResult | None:
        """Return a validated decision for an ambiguous job, or None to keep it ambiguous."""


class StructuredJsonLLMFallback:
    """Provider-neutral adapter around a configured structured-JSON LLM call.

    The injected callable owns provider authentication and transport. This keeps the core free
    from an AI dependency and guarantees that only ambiguous newly discovered roles are sent.
    """

    def __init__(
        self, request_json: Callable[[str], Awaitable[str | Mapping[str, object]]]
    ) -> None:
        self.request_json = request_json

    async def classify(self, job: Job) -> ClassificationResult | None:
        prompt = self._prompt(job)
        raw = await self.request_json(prompt)
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        try:
            classification = Classification(str(payload["classification"]))
            confidence = float(payload["confidence"])
            reason = str(payload["reason"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("LLM fallback returned invalid structured JSON") from exc
        if classification is Classification.IRRELEVANT and confidence < 0.9:
            return None
        return ClassificationResult(classification, reason, confidence)

    @staticmethod
    def _prompt(job: Job) -> str:
        description = (job.description or "")[:12_000]
        return f"""Classify this newly discovered software-oriented job for two US profiles:
- internship: May 2028 graduation, Winter/Spring/Summer 2027
- new grad: May 2027 graduation, starting in 2027

Prefer recall. Return JSON only with classification (INTERN_2027, NEW_GRAD_2027,
RELEVANT_BUT_AMBIGUOUS, or IRRELEVANT), confidence from 0 to 1, and a short reason.

Company: {job.company}
Title: {job.title}
Location: {job.location or "unknown"}
Employment type: {job.employment_type or "unknown"}
Description:
{description}"""
