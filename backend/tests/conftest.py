"""Test fixtures."""

import sys
from unittest.mock import MagicMock

# Heavy ML deps (torch) are not required for unit tests; stub when absent
# so the suite runs on machines/CI runners without GPU wheels installed.
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    sys.modules["sentence_transformers"] = MagicMock()

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
