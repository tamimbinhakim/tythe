import { useState } from "react";
import { ResultNarrowing } from "./pages/01-result-narrowing.tsx";
import { ExhaustiveSwitch } from "./pages/02-exhaustive-switch.tsx";
import { EnumConsts } from "./pages/03-enum-consts.tsx";
import { NamespaceContract } from "./pages/04-namespace-contract.tsx";

const PAGES = [
  { slug: "result", label: "Result narrowing", Component: ResultNarrowing },
  { slug: "exhaustive", label: "Exhaustive switch", Component: ExhaustiveSwitch },
  { slug: "enums", label: "Enum consts", Component: EnumConsts },
  { slug: "namespace", label: "Routes namespace", Component: NamespaceContract },
] as const;

type Slug = (typeof PAGES)[number]["slug"];

export function App() {
  const [active, setActive] = useState<Slug>(PAGES[0].slug);
  const Page = (PAGES.find((p) => p.slug === active) ?? PAGES[0]).Component;
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 880, margin: "32px auto" }}>
      <h1 style={{ marginBottom: 4 }}>Tythe · type-safety tour</h1>
      <p style={{ color: "#666", marginTop: 0 }}>
        Each page demos one thing the generated client buys you. Open the source — what TypeScript
        sees is the whole show.
      </p>
      <nav style={{ display: "flex", gap: 8, marginBottom: 24, flexWrap: "wrap" }}>
        {PAGES.map((p) => (
          <button
            key={p.slug}
            onClick={() => setActive(p.slug)}
            style={{
              padding: "6px 14px",
              border: "1px solid #ddd",
              borderRadius: 999,
              background: p.slug === active ? "#111" : "#fff",
              color: p.slug === active ? "#fff" : "#111",
              cursor: "pointer",
            }}
          >
            {p.label}
          </button>
        ))}
      </nav>
      <Page />
    </main>
  );
}
