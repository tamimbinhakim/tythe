"""Cover the output-format helpers of tythe.diff."""

# pyright: basic

from __future__ import annotations

import json as _json

from tythe.diff import Change, DiffResult, format_github, format_human, format_json


def _result(*changes: Change) -> DiffResult:
    r = DiffResult()
    for c in changes:
        r.changes.append(c)
    return r


def test_human_no_changes() -> None:
    out = format_human(_result())
    assert "no changes" in out


def test_human_marks_breaking_first() -> None:
    r = _result(
        Change("breaking", "route-removed", "x", route="x"),
        Change("info", "route-added", "y", route="y"),
    )
    out = format_human(r)
    assert "breaking" in out
    assert "additive" in out


def test_json_format_round_trip() -> None:
    r = _result(Change("breaking", "x-removed", "x route gone", route="x"))
    parsed = _json.loads(format_json(r))
    assert parsed["changes"][0] == {
        "severity": "breaking",
        "code": "x-removed",
        "message": "x route gone",
        "route": "x",
    }


def test_github_format_emits_workflow_commands() -> None:
    r = _result(
        Change("breaking", "x-removed", "x gone", route="x"),
        Change("info", "y-added", "y new", route="y"),
    )
    out = format_github(r)
    assert "::error" in out
    assert "::notice" in out
    assert "title=tythe-diff" in out
