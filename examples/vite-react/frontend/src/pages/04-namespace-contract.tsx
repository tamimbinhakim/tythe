import { useState } from "react";
import type { Err, Ok } from "@tythe/ts";
import { api, type Routes } from "../lib/tythe/client";

const AUTH = { authorization: "Bearer 1" };

// `Routes.X.Args / Data / Error / Return` are auto-generated. Helpers can
// declare what subset of a route's shape they accept without anyone re-typing
// the unions by hand.

// 1. Function signature pinned to a route's error union:
function showError(err: Routes.transitionIssue.Error): string {
  switch (err.kind) {
    case "IssueNotFound":
      return `(${err.kind}) id=${err.issueId}`;
    case "InvalidStatusTransition":
      return `(${err.kind}) ${err.fromStatus} → ${err.toStatus}`;
    case "Forbidden":
      return `(${err.kind}) ${err.reason}`;
  }
}

// 2. Pull the success type out of a `Promise<Result<…>>` Return without nesting
//    `Awaited<>` + manual extraction:
type IssueData = Ok<Routes.getIssue.Return>; //                = Issue
type IssueErr = Err<Routes.getIssue.Return>; //                = IssueNotFound | Forbidden

// 3. Pass the exact Args type to a wrapper that re-shapes a form:
async function callWithArgs(args: Routes.createIssue.Args) {
  return api.createIssue(args, { headers: AUTH });
}

export function NamespaceContract() {
  const [out, setOut] = useState("Click to run.");

  async function run() {
    const lookup: IssueData | IssueErr = await api
      .getIssue({ issueId: 999 }, { headers: AUTH })
      .then((r) => (r.ok ? r.data : r.error));

    const created = await callWithArgs({
      data: { title: "via Routes.createIssue.Args", body: "demo" },
    });

    const failed = await api.transitionIssue({ issueId: 1, to: "blocked" }, { headers: AUTH });

    setOut(
      [
        `getIssue(999): ${"kind" in lookup ? `× ${showError(lookup as Routes.transitionIssue.Error)}` : `✓ ${lookup.title}`}`,
        `createIssue: ${created.ok ? `✓ #${created.data.id}` : `× ${created.error.kind}`}`,
        `transitionIssue: ${failed.ok ? `✓ ${failed.data.status}` : `× ${showError(failed.error)}`}`,
      ].join("\n"),
    );
  }

  return (
    <section>
      <h2>Routes namespace as a contract</h2>
      <p style={{ color: "#666" }}>
        Helpers below all reference <code>Routes.X.*</code> aliases. None of these unions are
        hand-written.
      </p>
      <button onClick={run}>run three calls</button>
      <pre style={{ background: "#f5f5f5", padding: 12, marginTop: 16, whiteSpace: "pre-wrap" }}>
        {out}
      </pre>
    </section>
  );
}
