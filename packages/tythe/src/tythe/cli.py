"""``tythe`` CLI.

- ``tythe init``      — scaffold ``server/app.py`` + a ``tythe.toml``.
- ``tythe codegen``   — emit ``client.ts`` once and exit.
- ``tythe dev``       — run uvicorn with reload, watch the server tree, and
                         atomically rewrite ``client.ts`` on every change.
- ``tythe build``     — emit ``client.ts`` then start uvicorn without the watcher.

The dev watcher does the writes *atomically* (tmp + rename) so the TS toolchain
never reads a half-written file mid-rebuild — that single detail is what makes
"forget the codegen exists" actually feel like it.
"""

from __future__ import annotations

import asyncio
import importlib
import signal
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich import print as rprint
from rich.console import Console
from watchfiles import awatch

from tythe import __version__
from tythe.app import App
from tythe.codegen import write as write_client
from tythe.ir import build_ir

app_cli = typer.Typer(
    name="tythe",
    help="A type-safe RPC bridge between Python and TypeScript. The function signature is the contract.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


def _load_app(target: str) -> App:
    module_name, _, attr = target.partition(":")
    if not module_name or not attr:
        raise typer.BadParameter("Target must be 'module:attr', e.g. 'server.app:app'.")
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    if not isinstance(obj, App):
        raise typer.BadParameter(f"{target} is not a tythe.App instance.")
    return obj


def _regenerate(target: str, out: Path) -> int:
    """Re-import the target module so handler edits show up, then write the client."""
    module_name = target.partition(":")[0]
    mod = sys.modules.get(module_name)
    if mod is not None:
        importlib.reload(mod)
    app = _load_app(target)
    ir = build_ir(app)
    write_client(ir, out)
    return len(ir.routes)


@app_cli.command()
def version() -> None:
    """Print the installed Tythe version."""
    rprint(f"tythe [bold]{__version__}[/bold]")


@app_cli.command()
def init(
    target: Annotated[Path, typer.Option(help="Where to scaffold")] = Path("server"),
    out: Annotated[Path, typer.Option(help="Where the client.ts will be written")] = Path(
        "src/lib/tythe/client.ts",
    ),
) -> None:
    """Scaffold a minimal Tythe server and wire the client output path."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").touch()
    app_py = target / "app.py"
    if app_py.exists():
        rprint(f"[yellow]exists[/yellow] {app_py}")
    else:
        app_py.write_text(_STARTER_APP, encoding="utf-8")
        rprint(f"[green]wrote[/green]   {app_py}")

    config = Path("tythe.toml")
    if config.exists():
        rprint(f"[yellow]exists[/yellow] {config}")
    else:
        config.write_text(_STARTER_CONFIG.format(target=f"{target.name}.app:app", out=out))
        rprint(f"[green]wrote[/green]   {config}")

    rprint("\n[dim]Next:[/dim] [bold]tythe dev[/bold]")


@app_cli.command()
def codegen(
    target: Annotated[str, typer.Argument(help="module:attr of your tythe.App")],
    out: Annotated[Path, typer.Option(help="Where to write client.ts")] = Path(
        "src/lib/tythe/client.ts",
    ),
) -> None:
    """Generate the TypeScript client once and exit."""
    app = _load_app(target)
    ir = build_ir(app)
    write_client(ir, out)
    rprint(f"[bold green]wrote[/bold green] {out} ({len(ir.routes)} routes)")


@app_cli.command()
def dev(
    target: Annotated[str, typer.Argument(help="module:attr of your tythe.App")],
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
    out: Annotated[Path, typer.Option(help="Where to write client.ts")] = Path(
        "src/lib/tythe/client.ts",
    ),
    watch: Annotated[Path, typer.Option(help="Source directory to watch")] = Path("."),
) -> None:
    """Run uvicorn with reload and regenerate ``client.ts`` on every change."""
    routes = _regenerate(target, out)
    rprint(f"[bold green]wrote[/bold green] {out} ({routes} routes)")

    # uvicorn handles handler hot-reload; we just keep the client.ts fresh on
    # every change so the TS toolchain always sees the latest types.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            target,
            "--host",
            host,
            "--port",
            str(port),
            "--reload",
            "--reload-dir",
            str(watch),
        ],
    )

    async def watch_loop() -> None:
        async for _changes in awatch(watch, recursive=True, watch_filter=_py_only):
            try:
                routes = _regenerate(target, out)
                rprint(f"[dim]regen[/dim]   {out} ({routes} routes)")
            except Exception as exc:
                console.print_exception()
                rprint(f"[red]regen failed:[/red] {exc}")

    try:
        asyncio.run(watch_loop())
    except KeyboardInterrupt:
        pass
    finally:
        proc.send_signal(signal.SIGINT)
        proc.wait()


@app_cli.command()
def build(
    target: Annotated[str, typer.Argument(help="module:attr of your tythe.App")],
    host: Annotated[str, typer.Option()] = "0.0.0.0",
    port: Annotated[int, typer.Option()] = 8000,
    out: Annotated[Path, typer.Option(help="Where to write client.ts")] = Path(
        "src/lib/tythe/client.ts",
    ),
) -> None:
    """Generate ``client.ts`` and start uvicorn without the watcher."""
    routes = _regenerate(target, out)
    rprint(f"[bold green]wrote[/bold green] {out} ({routes} routes)")
    uvicorn.run(target, host=host, port=port)


def _py_only(_change: object, path: str) -> bool:
    return path.endswith(".py")


_STARTER_APP = '''"""A minimal Tythe server. Edit me."""

from __future__ import annotations

from tythe import App

app = App()


@app.get("/")
async def root() -> dict[str, str]:
    return {"hello": "world"}
'''

_STARTER_CONFIG = """# tythe.toml — config for the `tythe` CLI.

[server]
target = "{target}"

[client]
out = "{out}"
"""


def main() -> None:
    app_cli()


if __name__ == "__main__":
    main()
