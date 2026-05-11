import { useState } from "react";
import { api } from "../lib/tythe/client";

const AUTH = { authorization: "Bearer 1" };

// The route declares `@raises(IssueNotFound, Forbidden)`. On the TS side that's
// `Result<Issue, IssueNotFound | Forbidden>` — `result.error.kind` is the only
// way in, and TypeScript narrows each branch to its concrete shape.

export function ResultNarrowing() {
  const [out, setOut] = useState("Click a button.");

  async function go(issueId: number) {
    const result = await api.getIssue({ issueId }, { headers: AUTH });
    if (result.ok) {
      // result.data: Issue
      setOut(`✓ ${result.data.title}`);
      return;
    }
    switch (result.error.kind) {
      case "IssueNotFound":
        // result.error narrowed to { kind: "IssueNotFound"; issueId: number }
        setOut(`× IssueNotFound — id=${result.error.issueId}`);
        return;
      case "Forbidden":
        // result.error narrowed to { kind: "Forbidden"; reason: string }
        setOut(`× Forbidden — ${result.error.reason}`);
        return;
    }
  }

  return (
    <section>
      <h2>Result narrowing</h2>
      <button onClick={() => go(1)}>existing id</button>
      <button onClick={() => go(999)}>missing id (→ IssueNotFound)</button>
      <pre style={{ background: "#f5f5f5", padding: 12, marginTop: 16 }}>{out}</pre>
    </section>
  );
}
