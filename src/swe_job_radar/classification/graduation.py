from __future__ import annotations

import calendar
import re
from datetime import date

MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name})


def extract_month_years(text: str) -> list[date]:
    matches: list[date] = []
    pattern = r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(20\d{2})\b"
    for month, year in re.findall(pattern, text, flags=re.IGNORECASE):
        matches.append(date(int(year), MONTHS[month.casefold()], 1))
    return matches


def graduation_window_matches(text: str, target: date) -> bool | None:
    lowered = text.casefold()
    graduation_context = re.search(
        r".{0,80}(?:graduat(?:e|es|ing|ion)|degree|student).{0,180}",
        lowered,
        re.DOTALL,
    )
    if not graduation_context:
        return None
    context = graduation_context.group()
    dates = extract_month_years(context)
    if len(dates) >= 2:
        start, end = min(dates), max(dates)
        return start <= target <= end
    if len(dates) == 1:
        return dates[0].year == target.year
    years = {int(year) for year in re.findall(r"\b20\d{2}\b", context)}
    if years:
        return target.year in years
    return None
