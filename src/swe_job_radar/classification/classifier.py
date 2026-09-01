from __future__ import annotations

import re
from datetime import date

from swe_job_radar.classification.graduation import graduation_window_matches
from swe_job_radar.classification.rules import (
    INTERN_PATTERNS,
    NEW_GRAD_PATTERNS,
    NON_TECH_PATTERNS,
    QUANT_EXCLUSIONS,
    SENIOR_TITLE_PATTERNS,
    TECH_PATTERNS,
    contains_any,
    required_experience_years,
)
from swe_job_radar.models import Classification, ClassificationResult, Job, Priority

US_MARKERS = (
    "united states",
    "usa",
    "u.s.",
    "us remote",
    "remote (us)",
    "remote - us",
    "nyc",
    "san francisco",
    "new york",
    "seattle",
    "austin",
    "boston",
    "chicago",
    "atlanta",
    "washington, dc",
    "mountain view",
    "sunnyvale",
    "palo alto",
    "los angeles",
)
NON_US_MARKERS = (
    "london",
    "dublin",
    "singapore",
    "tokyo",
    "india",
    "canada",
    "australia",
    "germany",
    "france",
    "poland",
    "netherlands",
    "hong kong",
    "hkg",
    "ldn",
    "sgp",
    "ams",
    "mum",
    "sha",
)


class RuleBasedClassifier:
    def classify(self, job: Job, priority: Priority) -> ClassificationResult:
        title = job.title.strip()
        description = job.description or ""
        text = f"{title}\n{job.employment_type or ''}\n{description}"
        explicit_early = contains_any(text, INTERN_PATTERNS + NEW_GRAD_PATTERNS)

        if not contains_any(title, TECH_PATTERNS):
            return ClassificationResult(
                Classification.IRRELEVANT, "Title is not a software-oriented technical role.", 0.97
            )
        if contains_any(title, NON_TECH_PATTERNS) and not re.search(
            r"software|developer|infrastructure|systems", title, re.IGNORECASE
        ):
            return ClassificationResult(
                Classification.IRRELEVANT, "Title matches an excluded non-SWE function.", 0.98
            )
        if (
            priority is Priority.QUANT
            and contains_any(title, QUANT_EXCLUSIONS)
            and not re.search(
                r"software|developer|systems|infrastructure|platform", title, re.IGNORECASE
            )
        ):
            return ClassificationResult(
                Classification.IRRELEVANT, "Quant-firm role is not software-oriented.", 0.99
            )
        if contains_any(title, SENIOR_TITLE_PATTERNS) and not explicit_early:
            return ClassificationResult(
                Classification.IRRELEVANT, "Title indicates senior-level responsibility.", 0.99
            )
        experience = required_experience_years(description)
        if experience and max(experience) >= 3 and not explicit_early:
            return ClassificationResult(
                Classification.IRRELEVANT,
                f"Posting requires at least {max(experience)} years of experience.",
                0.96,
            )
        if self._clearly_non_us(job.location):
            return ClassificationResult(
                Classification.IRRELEVANT, "Posting is explicitly outside the United States.", 0.94
            )

        internship = contains_any(text, INTERN_PATTERNS)
        new_grad = contains_any(text, NEW_GRAD_PATTERNS)
        years = {int(year) for year in re.findall(r"\b20\d{2}\b", text)}

        if internship:
            graduation = graduation_window_matches(text, date(2028, 5, 1))
            if graduation is False:
                return ClassificationResult(
                    Classification.IRRELEVANT,
                    "Explicit graduation window excludes May 2028.",
                    0.96,
                )
            target_season = re.search(
                r"(?:summer|winter|spring|intern(?:ship)?|co-?op).{0,30}2027"
                r"|2027.{0,30}(?:summer|winter|spring|intern(?:ship)?|co-?op)",
                text,
                re.IGNORECASE,
            )
            other_season = re.search(
                r"(?:summer|winter|spring|internship).{0,20}(?:2026|2028|2029)"
                r"|(?:2026|2028|2029).{0,20}(?:summer|winter|spring|internship)",
                text,
                re.IGNORECASE,
            )
            if target_season:
                return ClassificationResult(
                    Classification.INTERN_2027,
                    "Software-oriented 2027 internship/co-op compatible with the target profile.",
                    0.94 if graduation is not False else 0.8,
                )
            if other_season:
                return ClassificationResult(
                    Classification.IRRELEVANT,
                    "Internship explicitly targets a year other than 2027.",
                    0.9,
                )
            return ClassificationResult(
                Classification.RELEVANT_BUT_AMBIGUOUS,
                "Strong SWE internship signal, but the 2027 season is not explicit.",
                0.82,
            )

        if new_grad:
            graduation = graduation_window_matches(text, date(2027, 5, 1))
            if graduation is False:
                return ClassificationResult(
                    Classification.IRRELEVANT,
                    "Explicit graduation window excludes May 2027.",
                    0.96,
                )
            if not years or 2027 in years or graduation is True:
                return ClassificationResult(
                    Classification.NEW_GRAD_2027,
                    "Early-career SWE requirements are compatible with a May 2027 graduate.",
                    0.92,
                )
            return ClassificationResult(
                Classification.RELEVANT_BUT_AMBIGUOUS,
                "Early-career SWE role has a non-target or unclear start year.",
                0.78,
            )

        return ClassificationResult(
            Classification.RELEVANT_BUT_AMBIGUOUS,
            "Software-oriented role, but internship/new-grad eligibility is not explicit.",
            0.7,
        )

    @staticmethod
    def _clearly_non_us(location: str | None) -> bool:
        if not location:
            return False
        lowered = location.casefold()
        return any(marker in lowered for marker in NON_US_MARKERS) and not any(
            marker in lowered for marker in US_MARKERS
        )
