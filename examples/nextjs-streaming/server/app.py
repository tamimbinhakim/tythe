"""Deploy pipeline — typed streaming over SSE.

What a single ``stream[T1 | T2 | ...]`` annotation buys you on the TS side:

- the client receives an ``AsyncIterable`` of the *exact* discriminated union
- ``ev.kind`` narrows each event to its concrete shape
- adding a new event variant on the server fails the TS build until it's
  handled (or explicitly ignored) — same compile-time safety as redux discriminated
  reducers, but the union is generated, not hand-written
"""

# pyright: basic
# msgspec ships incomplete stubs for ``Struct(tag=..., tag_field=...)``;
# basic mode skips those false errors without weakening the demo.

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import msgspec

from tythe import App, raises, stream

app = App()

Phase = Literal["provision", "build", "deploy"]
Level = Literal["info", "warn", "error"]


class Provisioning(msgspec.Struct, tag_field="kind", tag="provisioning"):
    phase: Phase
    started_at: float


class BuildLog(msgspec.Struct, tag_field="kind", tag="build_log"):
    line: str
    level: Level
    at: float


class BuildArtifact(msgspec.Struct, tag_field="kind", tag="build_artifact"):
    name: str
    size_bytes: int
    sha256: str


class Deploying(msgspec.Struct, tag_field="kind", tag="deploying"):
    target: str
    region: str


class Deployed(msgspec.Struct, tag_field="kind", tag="deployed"):
    url: str
    revision: str
    elapsed_seconds: float


class FailedBuild(msgspec.Struct, tag_field="kind", tag="failed_build"):
    failing_step: str
    exit_code: int
    tail: list[str]


class FailedDeploy(msgspec.Struct, tag_field="kind", tag="failed_deploy"):
    target: str
    reason: str


DeployEvent = (
    Provisioning
    | BuildLog
    | BuildArtifact
    | Deploying
    | Deployed
    | FailedBuild
    | FailedDeploy
)


@dataclass
class JobNotFound(Exception):
    job_id: str


@app.get("/deployments/{job_id}/events")
@raises(JobNotFound)
async def watch_deployment(job_id: str) -> stream[DeployEvent]:
    """Run a fake deploy pipeline and emit typed events along the way.

    The shape of the union is what the TS side narrows on.
    """
    if job_id == "missing":
        raise JobNotFound(job_id=job_id)

    started = time.time()
    yield Provisioning(phase="provision", started_at=started)
    await asyncio.sleep(0.3)
    yield Provisioning(phase="build", started_at=time.time())

    for i, line in enumerate(["pulling deps", "compiling", "bundling", "minifying"]):
        await asyncio.sleep(0.25)
        yield BuildLog(line=line, level="warn" if i == 2 else "info", at=time.time())

    yield BuildArtifact(name="bundle.js", size_bytes=42_180, sha256="abc123def")

    # The "broken" job demonstrates the failure variants.
    if job_id == "broken":
        yield FailedBuild(
            failing_step="bundle",
            exit_code=1,
            tail=["error: missing module 'foo'", "stack trace here"],
        )
        return

    yield Provisioning(phase="deploy", started_at=time.time())
    await asyncio.sleep(0.3)
    yield Deploying(target="prod", region="iad1")
    await asyncio.sleep(0.4)

    if job_id == "rejected":
        yield FailedDeploy(target="prod", reason="quota exceeded")
        return

    yield Deployed(
        url=f"https://{job_id}.tythe-demo.dev",
        revision="rev_abc123",
        elapsed_seconds=time.time() - started,
    )
