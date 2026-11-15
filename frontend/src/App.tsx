import { useEffect, useState } from "react";
import { api } from "./api";
import { BenchPage } from "./pages/BenchPage";
import { CatalogPage } from "./pages/CatalogPage";
import { DesignPage } from "./pages/DesignPage";
import { SchematicPage } from "./pages/SchematicPage";

const PAGES = {
  catalog: { label: "Componentes", element: <CatalogPage /> },
  bench: { label: "Bancada de dispositivos", element: <BenchPage /> },
  design: { label: "Projeto", element: <DesignPage /> },
  simulator: { label: "Simulador", element: <SchematicPage /> },
} as const;
type PageKey = keyof typeof PAGES;

function initialPage(): PageKey {
  const hash = window.location.hash.replace("#", "");
  return hash in PAGES ? (hash as PageKey) : "catalog";
}

export default function App() {
  const [page, setPage] = useState<PageKey>(initialPage);
  const [health, setHealth] = useState("verificando…");

  useEffect(() => {
    api
      .health()
      .then((h) => {
        const sim = h.simulator;
        setHealth(
          sim.shared_library || sim.executable
            ? `v${h.version} · ngspice ${sim.shared_library ? "(biblioteca)" : "(executável)"}`
            : `v${h.version} · ngspice não encontrado`,
        );
      })
      .catch(() => setHealth("servidor indisponível"));
  }, []);

  useEffect(() => {
    window.location.hash = page;
  }, [page]);

  return (
    <div className="app">
      <header>
        <h1>Projeto de Circuitos</h1>
        <nav aria-label="Seções">
          {(Object.keys(PAGES) as PageKey[]).map((key) => (
            <button
              key={key}
              className={key === page ? "tab active" : "tab"}
              aria-current={key === page ? "page" : undefined}
              onClick={() => setPage(key)}
            >
              {PAGES[key].label}
            </button>
          ))}
        </nav>
        <span className="muted small">{health}</span>
      </header>
      {PAGES[page].element}
    </div>
  );
}
