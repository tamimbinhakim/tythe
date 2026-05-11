"""CLI smoke tests (everything except the long-running dev loop)."""

# pyright: basic

from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from tythe import __version__
from tythe.cli import app_cli

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app_cli, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_codegen_writes_client(tmp_path: Path, monkeypatch) -> None:
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "app.py").write_text(
        textwrap.dedent(
            """
            from tythe import App
            app = App()
            @app.get("/ping")
            async def ping() -> str:
                return "pong"
            """,
        ),
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    out = tmp_path / "client.ts"
    result = runner.invoke(app_cli, ["codegen", "demo_pkg.app:app", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.exists()
    assert "AUTO-GENERATED" in out.read_text()


def test_init_scaffolds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app_cli, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "server" / "app.py").exists()
    assert (tmp_path / "tythe.toml").exists()
