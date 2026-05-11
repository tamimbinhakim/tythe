"use client";

import { useEffect, useRef, useState } from "react";
import { api, type BuildArtifact, type BuildLog, type Deployed } from "@/lib/tythe/client";

type State = {
  phase: "provision" | "build" | "deploy" | "done" | "failed";
  logs: BuildLog[];
  artifact: BuildArtifact | null;
  deployed: Deployed | null;
  failure: string | null;
};

const INITIAL: State = {
  phase: "provision",
  logs: [],
  artifact: null,
  deployed: null,
  failure: null,
};

export default function Page() {
  const [jobId, setJobId] = useState("demo");
  const [state, setState] = useState<State>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    abortRef.current = ac;
    setState(INITIAL);

    (async () => {
      try {
        // The union TS sees here is identical to the Python `stream[...]`. Every
        // `ev.kind` branch below narrows to the exact event shape — no casts,
        // no `any`. Add a new event variant on the server and the codegen will
        // expand this union; TS will then flag the `switch` as non-exhaustive
        // until you handle (or explicitly drop) the new case.
        for await (const ev of api.watchDeployment({ jobId }, { signal: ac.signal })) {
          setState((s) => {
            switch (ev.kind) {
              case "provisioning":
                return { ...s, phase: ev.phase };
              case "build_log":
                return { ...s, logs: [...s.logs, ev] };
              case "build_artifact":
                return { ...s, artifact: ev };
              case "deploying":
                return { ...s, phase: "deploy" };
              case "deployed":
                return { ...s, phase: "done", deployed: ev };
              case "failed_build":
                return {
                  ...s,
                  phase: "failed",
                  failure: `${ev.failingStep} exited ${ev.exitCode}\n${ev.tail.join("\n")}`,
                };
              case "failed_deploy":
                return { ...s, phase: "failed", failure: `${ev.target}: ${ev.reason}` };
            }
          });
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setState((s) => ({ ...s, phase: "failed", failure: (err as Error).message }));
      }
    })();

    return () => ac.abort();
  }, [jobId]);

  return (
    <main style={{ maxWidth: 720, margin: "0 auto" }}>
      <h1>Deploy pipeline</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        {(["demo", "broken", "rejected", "missing"] as const).map((j) => (
          <button
            key={j}
            onClick={() => setJobId(j)}
            style={{
              padding: "6px 12px",
              background: j === jobId ? "#222" : "#eee",
              color: j === jobId ? "#fff" : "#222",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            {j}
          </button>
        ))}
      </div>

      <Phases phase={state.phase} />

      {state.logs.length > 0 && (
        <pre
          style={{
            background: "#0b0b0b",
            color: "#9efd9e",
            padding: 16,
            borderRadius: 8,
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          {state.logs.map((l, i) => (
            <div key={i} style={{ color: levelColor(l.level) }}>
              [{l.level}] {l.line}
            </div>
          ))}
        </pre>
      )}

      {state.artifact && (
        <p>
          🧱 <strong>{state.artifact.name}</strong> · {state.artifact.sizeBytes} bytes ·{" "}
          <code>{state.artifact.sha256}</code>
        </p>
      )}

      {state.deployed && (
        <p>
          ✅ Live at{" "}
          <a href={state.deployed.url} target="_blank" rel="noreferrer">
            {state.deployed.url}
          </a>{" "}
          ({state.deployed.elapsedSeconds.toFixed(1)}s, rev {state.deployed.revision})
        </p>
      )}

      {state.failure && <p style={{ color: "crimson" }}>❌ {state.failure}</p>}
    </main>
  );
}

function Phases({ phase }: { phase: State["phase"] }) {
  const ALL = ["provision", "build", "deploy", "done"] as const;
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 24 }}>
      {ALL.map((p) => (
        <span
          key={p}
          style={{
            padding: "4px 10px",
            borderRadius: 20,
            background: p === phase ? "#0070f3" : "#eee",
            color: p === phase ? "#fff" : "#444",
            fontSize: 12,
          }}
        >
          {p}
        </span>
      ))}
      {phase === "failed" && (
        <span
          style={{
            padding: "4px 10px",
            borderRadius: 20,
            background: "crimson",
            color: "#fff",
            fontSize: 12,
          }}
        >
          failed
        </span>
      )}
    </div>
  );
}

function levelColor(level: BuildLog["level"]) {
  return level === "error" ? "#ff6b6b" : level === "warn" ? "#ffd166" : "#9efd9e";
}
