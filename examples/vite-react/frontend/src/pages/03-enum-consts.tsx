import { useState } from "react";
import { api, IssuePriority, IssueStatus } from "../lib/tythe/client";

const AUTH = { authorization: "Bearer 1" };

// The codegen emits `<Struct><Field>` value-objects for every `Literal[...]`
// field. Type `IssueStatus.` and the IDE shows the four valid values; rename
// `"closed"` → `"resolved"` on the Python side and every call site fails on
// regen until you migrate.

export function EnumConsts() {
  const [out, setOut] = useState("Click to create.");

  async function go() {
    const result = await api.createIssue(
      {
        data: {
          title: "Demo issue",
          body: "value-object const used for `priority`",
          priority: IssuePriority.Urgent, //                                ← rename-safe
          labelNames: ["bug", "frontend"],
        },
      },
      { headers: AUTH },
    );
    if (!result.ok) return setOut(`× ${result.error.kind}: ${result.error.reason}`);
    setOut(`✓ created #${result.data.id} — ${result.data.title} (${result.data.priority})`);
  }

  return (
    <section>
      <h2>Enum value-object consts</h2>
      <p style={{ color: "#666" }}>
        Generated for every <code>Literal[...]</code> field on a Struct.
      </p>
      <button onClick={go}>create with IssuePriority.Urgent</button>
      <pre style={{ background: "#f5f5f5", padding: 12, marginTop: 16 }}>{out}</pre>
      <p style={{ color: "#888", fontSize: 13 }}>
        Generated consts available here: <code>IssueStatus</code> (
        {Object.values(IssueStatus).join(", ")}
        ), <code>IssuePriority</code> ({Object.values(IssuePriority).join(", ")}).
      </p>
    </section>
  );
}
