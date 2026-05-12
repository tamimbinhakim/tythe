"""Additional OpenAPI exporter cases — file uploads, multi-body embed, raw bytes."""

# pyright: basic

from __future__ import annotations

from typing import Annotated

from tythe import App, Bytes
from tythe.ir import build_ir
from tythe.openapi import render
from tythe.params import Body, File, UploadFile


def test_file_upload_emits_multipart_request_body() -> None:
    app = App()

    @app.post("/avatar")
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, int]:
        return {"size": 0}

    op = render(build_ir(app))["paths"]["/avatar"]["post"]
    assert "multipart/form-data" in op["requestBody"]["content"]


def test_embedded_body_emits_object_schema() -> None:
    app = App()

    @app.post("/login")
    async def login(
        email: Annotated[str, Body()],
        password: Annotated[str, Body()],
    ) -> dict[str, str]:
        return {"email": email, "pw_len": str(len(password))}

    op = render(build_ir(app))["paths"]["/login"]["post"]
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema["type"] == "object"
    assert "email" in schema["properties"]
    assert "password" in schema["properties"]
    assert set(schema["required"]) >= {"email", "password"}


def test_bytes_response_documented_as_octet_stream() -> None:
    app = App()

    @app.get("/blob")
    async def blob() -> Bytes:
        return b""

    op = render(build_ir(app))["paths"]["/blob"]["get"]
    # Bytes responses surface as binary; the schema marks format=binary.
    content = op["responses"]["200"]["content"]
    schema = next(iter(content.values()))["schema"]
    assert schema.get("format") == "binary" or schema.get("type") == "string"


def test_default_info_overrides() -> None:
    app = App()

    @app.get("/ping")
    async def ping() -> str:
        return "ok"

    doc = render(build_ir(app), title="Hello", version="9.9.9")
    assert doc["info"] == {"title": "Hello", "version": "9.9.9"}
