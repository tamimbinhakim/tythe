"""Issue tracker — exercising the full type-safety surface.

What this server demos, end-to-end:

- discriminated-union responses (status, priority, error kinds)
- path + query + body + header params on the same handler
- a header-based ``Depends(...)`` resolving the current user
- ``@raises(...)`` with multiple error kinds per route
- nested types with optional fields and arrays of unions
- a streaming endpoint that yields a multi-variant event union
"""

# pyright: basic
# msgspec ships incomplete stubs for ``Struct(tag=..., tag_field=...)``;
# basic mode skips those false errors without weakening the demo.

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Annotated, Literal

import msgspec
from tythe import App, Context, Depends, raises, stream
from tythe.params import Header, Query

app = App()

# ----------------------------- domain types --------------------------------

Priority = Literal["low", "medium", "high", "urgent"]
Status = Literal["open", "in_progress", "blocked", "closed"]


class Label(msgspec.Struct):
    name: str
    color: str  # hex


class User(msgspec.Struct):
    id: int
    name: str
    email: str


class Comment(msgspec.Struct):
    id: int
    author: User
    body: str
    created_at: float


class Issue(msgspec.Struct):
    id: int
    title: str
    body: str
    status: Status
    priority: Priority
    assignee: User | None
    labels: list[Label]
    comments: list[Comment]
    created_at: float
    updated_at: float


class IssueSummary(msgspec.Struct):
    """A trimmed view used in list endpoints."""

    id: int
    title: str
    status: Status
    priority: Priority
    assignee: User | None
    label_names: list[str]


class CreateIssue(msgspec.Struct):
    title: str
    body: str
    priority: Priority = "medium"
    label_names: list[str] = []


class UpdateIssue(msgspec.Struct):
    title: str | None = None
    body: str | None = None
    priority: Priority | None = None


class Page(msgspec.Struct):
    items: list[IssueSummary]
    next_cursor: str | None
    total: int


# ----------------------------- typed errors --------------------------------


@dataclass
class IssueNotFound(Exception):
    issue_id: int


@dataclass
class Forbidden(Exception):
    reason: str


@dataclass
class InvalidStatusTransition(Exception):
    from_status: Status
    to_status: Status
    allowed: list[Status]


@dataclass
class CommentRateLimited(Exception):
    retry_after_seconds: int


# ----------------------------- fake store ----------------------------------

_ISSUES: dict[int, Issue] = {}
_next_id = 1
_USERS: dict[int, User] = {
    1: User(id=1, name="Ada Lovelace", email="ada@example.com"),
    2: User(id=2, name="Grace Hopper", email="grace@example.com"),
}

_TRANSITIONS: dict[Status, list[Status]] = {
    "open": ["in_progress", "closed"],
    "in_progress": ["blocked", "closed"],
    "blocked": ["in_progress", "closed"],
    "closed": [],
}


# ----------------------------- auth dep ------------------------------------


def current_user(authorization: Annotated[str, Header()] = "") -> User:
    """Resolve a user from a bearer token of the form ``Bearer <user_id>``.

    Toy implementation for the demo — real apps would hit auth0/clerk/etc.
    """
    if not authorization.startswith("Bearer "):
        raise Forbidden(reason="missing bearer token")
    try:
        uid = int(authorization.removeprefix("Bearer ").strip())
    except ValueError as exc:
        raise Forbidden(reason="malformed token") from exc
    user = _USERS.get(uid)
    if user is None:
        raise Forbidden(reason="unknown user")
    return user


# ----------------------------- handlers ------------------------------------


@app.get("/issues")
@raises(Forbidden)
async def list_issues(
    me: User = Depends(current_user),
    status: Annotated[Status | None, Query()] = None,
    priority: Annotated[Priority | None, Query()] = None,
    assignee_id: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query()] = 25,
) -> Page:
    del me  # auth side-effect only
    items = list(_ISSUES.values())
    if status is not None:
        items = [i for i in items if i.status == status]
    if priority is not None:
        items = [i for i in items if i.priority == priority]
    if assignee_id is not None:
        items = [i for i in items if i.assignee and i.assignee.id == assignee_id]
    if search:
        q = search.lower()
        items = [i for i in items if q in i.title.lower() or q in i.body.lower()]

    start = int(cursor) if cursor else 0
    end = start + limit
    window = items[start:end]
    return Page(
        items=[
            IssueSummary(
                id=i.id,
                title=i.title,
                status=i.status,
                priority=i.priority,
                assignee=i.assignee,
                label_names=[label.name for label in i.labels],
            )
            for i in window
        ],
        next_cursor=str(end) if end < len(items) else None,
        total=len(items),
    )


@app.get("/issues/{issue_id}")
@raises(IssueNotFound, Forbidden)
async def get_issue(issue_id: int, me: User = Depends(current_user)) -> Issue:
    del me
    issue = _ISSUES.get(issue_id)
    if issue is None:
        raise IssueNotFound(issue_id=issue_id)
    return issue


@app.post("/issues")
@raises(Forbidden)
async def create_issue(data: CreateIssue, me: User = Depends(current_user)) -> Issue:
    global _next_id
    now = time.time()
    issue = Issue(
        id=_next_id,
        title=data.title,
        body=data.body,
        status="open",
        priority=data.priority,
        assignee=me,
        labels=[Label(name=n, color="#888") for n in data.label_names],
        comments=[],
        created_at=now,
        updated_at=now,
    )
    _next_id += 1
    _ISSUES[issue.id] = issue
    return issue


@app.patch("/issues/{issue_id}")
@raises(IssueNotFound, Forbidden)
async def update_issue(
    issue_id: int,
    data: UpdateIssue,
    me: User = Depends(current_user),
) -> Issue:
    del me
    issue = _ISSUES.get(issue_id)
    if issue is None:
        raise IssueNotFound(issue_id=issue_id)
    if data.title is not None:
        issue.title = data.title
    if data.body is not None:
        issue.body = data.body
    if data.priority is not None:
        issue.priority = data.priority
    issue.updated_at = time.time()
    return issue


@app.post("/issues/{issue_id}/transition")
@raises(IssueNotFound, InvalidStatusTransition, Forbidden)
async def transition_issue(
    issue_id: int,
    to: Annotated[Status, Query()],
    me: User = Depends(current_user),
) -> Issue:
    del me
    issue = _ISSUES.get(issue_id)
    if issue is None:
        raise IssueNotFound(issue_id=issue_id)
    allowed = _TRANSITIONS[issue.status]
    if to not in allowed:
        raise InvalidStatusTransition(
            from_status=issue.status, to_status=to, allowed=allowed
        )
    issue.status = to
    issue.updated_at = time.time()
    return issue


@app.post("/issues/{issue_id}/comments")
@raises(IssueNotFound, CommentRateLimited, Forbidden)
async def add_comment(
    issue_id: int,
    body: Annotated[str, Query()],
    me: User = Depends(current_user),
) -> Comment:
    issue = _ISSUES.get(issue_id)
    if issue is None:
        raise IssueNotFound(issue_id=issue_id)
    if len(issue.comments) > 0 and time.time() - issue.comments[-1].created_at < 0.5:
        raise CommentRateLimited(retry_after_seconds=1)
    comment = Comment(
        id=len(issue.comments) + 1, author=me, body=body, created_at=time.time()
    )
    issue.comments.append(comment)
    issue.updated_at = time.time()
    return comment


# ----------------------------- streaming -----------------------------------


class ActivityCreated(msgspec.Struct, tag_field="kind", tag="created"):
    issue_id: int
    title: str
    by: User


class ActivityCommented(msgspec.Struct, tag_field="kind", tag="commented"):
    issue_id: int
    body: str
    by: User


class ActivityTransitioned(msgspec.Struct, tag_field="kind", tag="transitioned"):
    issue_id: int
    from_status: Status
    to_status: Status


@app.get("/activity")
async def activity_feed(
    ctx: Context,
) -> stream[ActivityCreated | ActivityCommented | ActivityTransitioned]:
    """Toy activity feed — emits a few fake events, then closes."""
    ada = _USERS[1]
    grace = _USERS[2]

    events: list[ActivityCreated | ActivityCommented | ActivityTransitioned] = [
        ActivityCreated(issue_id=1, title="Tune the watcher", by=ada),
        ActivityCommented(issue_id=1, body="Looks good, shipping it.", by=grace),
        ActivityTransitioned(issue_id=1, from_status="open", to_status="in_progress"),
    ]

    for ev in events:
        if await ctx.is_disconnected():
            break
        yield ev
        await asyncio.sleep(0.6)
