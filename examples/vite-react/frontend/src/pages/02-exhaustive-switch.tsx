import { useState } from "react";
import { api, IssueStatus, type Routes } from "../lib/tythe/client";

const AUTH = { authorization: "Bearer 1" };

// `Routes.transitionIssue.Error` is `IssueNotFound | InvalidStatusTransition |
// Forbidden`. The function below is typed against that union; remove a `case`
// and TypeScript flags the switch as non-exhaustive. Add an error variant on
// the Python side and the same check fires on next regen.

function describe(err: Routes.transitionIssue.Error): string {
  switch (err.kind) {
    case "IssueNotFound":
      return `IssueNotFound (id=${err.issueId})`;
    case "InvalidStatusTransition":
      return `InvalidStatusTransition ${err.fromStatus} → ${err.toStatus}. Try: ${err.allowed.join(", ")}.`;
    case "Forbidden":
      return `Forbidden — ${err.reason}`;
  }
}

export function ExhaustiveSwitch() {
  const [out, setOut] = useState("Click a button.");

  async function go(issueId: number, to: "blocked" | "closed" | "in_progress") {
    const result = await api.transitionIssue({ issueId, to }, { headers: AUTH });
    setOut(result.ok ? `✓ now ${result.data.status}` : `× ${describe(result.error)}`);
  }

  return (
    <section>
      <h2>Exhaustive switch over a 3-variant error union</h2>
      <button onClick={() => go(1, IssueStatus.InProgress)}>open → in_progress (ok)</button>
      <button onClick={() => go(1, IssueStatus.Blocked)}>open → blocked (illegal)</button>
      <button onClick={() => go(999, IssueStatus.Closed)}>missing id</button>
      <pre style={{ background: "#f5f5f5", padding: 12, marginTop: 16 }}>{out}</pre>
    </section>
  );
}
