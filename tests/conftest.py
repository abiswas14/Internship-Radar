from __future__ import annotations

import json
from pathlib import Path

from swe_job_radar.http import CachedResponse

FIXTURES = Path(__file__).parent / "fixtures"


class FakeHttp:
    def __init__(self, responses: dict[str, str | bytes]) -> None:
        self.responses = responses

    async def get(self, url: str, *, params: dict[str, object] | None = None) -> CachedResponse:
        value = self.responses[url]
        if isinstance(value, str):
            value = value.encode()
        return CachedResponse(value, None, None, 200, url)


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def load_json_fixture(name: str) -> object:
    return json.loads(load_fixture(name))
