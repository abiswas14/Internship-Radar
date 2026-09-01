from __future__ import annotations

import re

TECH_PATTERNS = (
    r"software",
    r"\bsde(?:\s+i)?\b",
    r"developer",
    r"backend",
    r"full[- ]stack",
    r"front[- ]?end engineer",
    r"mobile engineer",
    r"infrastructure",
    r"platform engineer",
    r"systems? engineer",
    r"distributed systems?",
    r"cloud engineer",
    r"site reliability",
    r"\bsre\b",
    r"security engineer",
    r"machine learning engineer",
    r"\bml engineer",
    r"\bai engineer",
    r"artificial intelligence engineer",
    r"quantitative (?:software )?(?:developer|engineer)",
    r"low[- ]latency.*engineer",
    r"trading systems engineer",
)

INTERN_PATTERNS = (
    r"\bintern(?:ship)?\b",
    r"\bco-?op\b",
    r"university intern",
    r"student",
)

NEW_GRAD_PATTERNS = (
    r"new grad(?:uate)?",
    r"university grad(?:uate)?",
    r"university hire",
    r"early career",
    r"recent graduate",
    r"entry[ -]level",
    r"campus",
    r"2027 (?:graduate|start)",
    r"0\s*(?:-|–|to)\s*1 years?",
    r"0 years? (?:of )?(?:professional )?experience",
)

SENIOR_TITLE_PATTERNS = (
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\bstaff\b",
    r"\bprincipal\b",
    r"\bdistinguished\b",
    r"engineering manager",
    r"\bdirector\b",
    r"\bvice president\b",
    r"\bvp\b",
    r"\barchitect\b",
)

NON_TECH_PATTERNS = (
    r"product manage",
    r"\bsales\b",
    r"marketing",
    r"\bfinance\b",
    r"accounting",
    r"\blegal\b",
    r"human resources",
    r"\bhr\b",
    r"recruit",
    r"mechanical engineer",
    r"electrical engineer",
    r"hardware engineer",
    r"business analyst",
    r"consultant",
    r"customer success",
)

QUANT_EXCLUSIONS = (
    r"quantitative researcher",
    r"quant research",
    r"\btrader\b",
    r"trading intern",
    r"investment analyst",
    r"portfolio analyst",
    r"fundamental research",
    r"research scientist",
    r"data scientist",
)


def contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def required_experience_years(text: str) -> list[int]:
    return [
        int(value)
        for value in re.findall(
            r"\b(\d{1,2})\s*\+?\s*years? (?:of )?"
            r"(?:professional |industry )?"
            r"(?:software (?:development |engineering )?|swe )?experience",
            text,
            flags=re.IGNORECASE,
        )
    ]
