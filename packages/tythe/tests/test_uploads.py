"""Multipart file upload tests."""

# pyright: basic
# Tests don't need strict typing; handlers are also consumed via decorator side effects.

from __future__ import annotations

from typing import Annotated

import httpx
import pytest

from tythe import App
from tythe.params import File, UploadFile


@pytest.fixture
def client_factory():
    def _make(app: App) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    return _make


async def test_upload_single_file(client_factory):
    app = App()

    @app.post("/upload")
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, object]:
        try:
            data = await file.read()
            return {"size": len(data), "name": file.filename}
        finally:
            await file.close()

    files = {"file": ("hello.txt", b"hello world", "text/plain")}
    async with client_factory(app) as client:
        r = await client.post("/upload", files=files)
    assert r.status_code == 200
    assert r.json() == {"size": 11, "name": "hello.txt"}


async def test_upload_plus_text_field(client_factory):
    app = App()

    @app.post("/profile")
    async def update_profile(
        avatar: Annotated[UploadFile, File()],
        bio: Annotated[str, File()] = "",
    ) -> dict[str, object]:
        try:
            data = await avatar.read()
            return {"avatar_size": len(data), "bio": bio}
        finally:
            await avatar.close()

    avatar_bytes = b"\x89PNG\r\n_FAKE"  # 10 bytes
    files = {"avatar": ("a.png", avatar_bytes, "image/png")}
    data = {"bio": "hello"}
    async with client_factory(app) as client:
        r = await client.post("/profile", files=files, data=data)
    assert r.json() == {"avatar_size": len(avatar_bytes), "bio": "hello"}
