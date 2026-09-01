from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser


class ScriptCaptureParser(HTMLParser):
    def __init__(self, *, script_id: str | None = None, script_type: str | None = None) -> None:
        super().__init__()
        self.script_id = script_id
        self.script_type = script_type
        self._capturing = False
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self._capturing = tag == "script" and (
            (self.script_id is not None and values.get("id") == self.script_id)
            or (self.script_type is not None and values.get("type") == self.script_type)
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self.values.append(data)


def html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"<(?:br|/p|/li|/h\d)>\s*", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
