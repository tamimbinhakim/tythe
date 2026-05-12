"""Diff between two IR snapshots."""

# pyright: basic

from __future__ import annotations

from typing import Any

from tythe.diff import diff_ir


def _route(
    name: str,
    method: str = "GET",
    path: str | None = None,
    params: list[dict[str, Any]] | None = None,
    response: dict[str, Any] | None = None,
    raises: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "method": method,
        "path": path or f"/{name}",
        "name": name,
        "params": params or [],
        "response": response,
        "streams": False,
        "event_schema": None,
        "raises": raises or [],
        "binary_body": False,
        "binary_response": False,
        "form_body": False,
    }


def test_no_changes() -> None:
    ir_value = {"routes": [_route("ping")], "components": {}}
    result = diff_ir(ir_value, ir_value)
    assert result.changes == []


def test_route_removed_is_breaking() -> None:
    old = {"routes": [_route("a"), _route("b")], "components": {}}
    new = {"routes": [_route("a")], "components": {}}
    result = diff_ir(old, new)
    breaking = [c.code for c in result.breaking]
    assert "route-removed" in breaking


def test_route_added_is_info() -> None:
    old = {"routes": [_route("a")], "components": {}}
    new = {"routes": [_route("a"), _route("b")], "components": {}}
    result = diff_ir(old, new)
    assert not result.breaking
    codes = [c.code for c in result.info]
    assert "route-added" in codes


def test_param_removed_is_breaking() -> None:
    old = {
        "routes": [
            _route(
                "get", params=[{"name": "id", "alias": "id", "location": "path", "required": True}]
            ),
        ],
        "components": {},
    }
    new = {"routes": [_route("get", params=[])], "components": {}}
    assert "param-removed" in [c.code for c in diff_ir(old, new).breaking]


def test_param_alias_change_is_breaking() -> None:
    old = {
        "routes": [
            _route(
                "get",
                params=[
                    {"name": "userId", "alias": "user_id", "location": "path", "required": True}
                ],
            ),
        ],
        "components": {},
    }
    new = {
        "routes": [
            _route(
                "get",
                params=[{"name": "userId", "alias": "uid", "location": "path", "required": True}],
            ),
        ],
        "components": {},
    }
    assert "param-alias-changed" in [c.code for c in diff_ir(old, new).breaking]


def test_optional_to_required_is_breaking() -> None:
    old = {
        "routes": [
            _route(
                "get", params=[{"name": "q", "alias": "q", "location": "query", "required": False}]
            ),
        ],
        "components": {},
    }
    new = {
        "routes": [
            _route(
                "get", params=[{"name": "q", "alias": "q", "location": "query", "required": True}]
            ),
        ],
        "components": {},
    }
    assert "param-now-required" in [c.code for c in diff_ir(old, new).breaking]


def test_new_required_param_is_breaking() -> None:
    old = {"routes": [_route("get", params=[])], "components": {}}
    new = {
        "routes": [
            _route(
                "get", params=[{"name": "q", "alias": "q", "location": "query", "required": True}]
            ),
        ],
        "components": {},
    }
    assert "param-added-required" in [c.code for c in diff_ir(old, new).breaking]


def test_response_field_removed_is_breaking() -> None:
    old = {
        "routes": [_route("u", response={"type": "object", "properties": {"id": {}, "name": {}}})],
        "components": {},
    }
    new = {
        "routes": [_route("u", response={"type": "object", "properties": {"id": {}}})],
        "components": {},
    }
    assert "response-property-removed" in [c.code for c in diff_ir(old, new).breaking]


def test_raises_change_is_breaking_both_ways() -> None:
    base = _route("u", raises=[{"name": "A", "schema": {}}, {"name": "B", "schema": {}}])
    removed = _route("u", raises=[{"name": "A", "schema": {}}])
    added = _route(
        "u",
        raises=[
            {"name": "A", "schema": {}},
            {"name": "B", "schema": {}},
            {"name": "C", "schema": {}},
        ],
    )
    assert "error-variant-removed" in [
        c.code
        for c in diff_ir(
            {"routes": [base], "components": {}}, {"routes": [removed], "components": {}}
        ).breaking
    ]
    assert "error-variant-added" in [
        c.code
        for c in diff_ir(
            {"routes": [base], "components": {}}, {"routes": [added], "components": {}}
        ).breaking
    ]


def test_method_or_path_change_is_breaking() -> None:
    old = {"routes": [_route("u", method="GET", path="/users")], "components": {}}
    new_method = {"routes": [_route("u", method="POST", path="/users")], "components": {}}
    new_path = {"routes": [_route("u", method="GET", path="/people")], "components": {}}
    assert "route-method-changed" in [c.code for c in diff_ir(old, new_method).breaking]
    assert "route-path-changed" in [c.code for c in diff_ir(old, new_path).breaking]
