from __future__ import annotations

import pytest

from pipeline.config import Settings


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.text = content.decode("utf-8")
        self.status_code = status_code
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def settings():
    return Settings.load()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"
