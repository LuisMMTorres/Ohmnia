import { useEffect, useState } from "react";
import { api } from "./api";
import { BenchPage } from "./pages/BenchPage";
import { CatalogPage } from "./pages/CatalogPage";
import { DesignPage } from "./pages/DesignPage";
import { ImportPage } from "./pages/ImportPage";
import { SchematicPage } from "./pages/SchematicPage";

const PAGES = {
  simulator: {
    label: "Simulador",
    description: "Monte o circuito, configure a análise e explore os resultados.",
    element: <SchematicPage />,
    icon: "M3 6h18v12H3z M7 10h4v4H7z M15 10h2 M15 14h2 M7 3v3 M17 3v3 M7 18v3 M17 18v3",
  },
  design: {
    label: "Análise de Projetos",
    description:
      "Transforme os requisitos em um projeto com componentes, margens e memória de cálculo.",
    element: <DesignPage />,
    icon: "M4 4h6v6H4z M14 14h6v6h-6z M10 7h7v7 M7 10v7h7",
  },
  catalog: {
    label: "Biblioteca",
    description: "Encontre peças reais, confira suas fontes e revise os parâmetros do catálogo.",
    element: <CatalogPage />,
    icon: "M6 6h12v12H6z M9 9h6v6H9z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4",
  },
  bench: {
    label: "Análise de dispositivos",
    description: "Explore curvas características e o comportamento de cada dispositivo.",
    element: <BenchPage />,
    icon: "M2 12h4l3-8 5 16 3-8h5",
  },
  imports: {
    label: "Importar datasheet",
    description: "Extraia parâmetros e confira cada valor ao lado do documento de origem.",
    element: <ImportPage />,
    icon: "M14 2H5v20h14V7z M14 2v6h5 M8 13h8 M8 17h6",
  },
} as const;
type PageKey = keyof typeof PAGES;

function initialPage(): PageKey {
  const hash = window.location.hash.replace("#", "");
  return hash in PAGES ? (hash as PageKey) : "simulator";
}

export default function App() {
  const [page, setPage] = useState<PageKey>(initialPage);
  const [health, setHealth] = useState({
    state: "checking",
    label: "Verificando simulador…",
    detail: "Servidor local",
  });

  useEffect(() => {
    api
      .health()
      .then((h) => {
        const sim = h.simulator;
        setHealth({
          state: sim.shared_library || sim.executable ? "ready" : "missing",
          label:
            sim.shared_library || sim.executable ? "ngspice disponível" : "ngspice não encontrado",
          detail: `v${h.version} · ${sim.shared_library ? "biblioteca" : sim.executable ? "executável" : "verifique a instalação"}`,
        });
      })
      .catch(() =>
        setHealth({
          state: "offline",
          label: "Servidor indisponível",
          detail: "Verifique o servidor local",
        }),
      );
  }, []);

  useEffect(() => {
    window.location.hash = page;
  }, [page]);

  useEffect(() => {
    const onHashChange = () => setPage(initialPage());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <div className={`app page-${page}`}>
      <a
        className="skip-link"
        href="#workspace-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("workspace-content")?.focus();
        }}
      >
        Ir para a área de trabalho
      </a>
      <header className="app-header">
        <div className="brand-row">
          <div className="app-brand">
            <span className="brand-symbol" aria-hidden="true">
              Ω
            </span>
            <h1>Ohmnia</h1>
            <span className="brand-caption">Projeto e simulação de circuitos</span>
          </div>
          <div className="health-status" data-state={health.state} role="status">
            <span className="health-dot" aria-hidden="true" />
            <span>
              {health.label}
              <small>{health.detail}</small>
            </span>
          </div>
        </div>
        <nav className="app-navigation" aria-label="Seções">
          {(Object.keys(PAGES) as PageKey[]).map((key) => (
            <button
              key={key}
              className={key === page ? "tab active" : "tab"}
              aria-current={key === page ? "page" : undefined}
              onClick={() => setPage(key)}
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d={PAGES[key].icon} />
              </svg>
              {PAGES[key].label}
            </button>
          ))}
        </nav>
      </header>
      <div id="workspace-content" className="workspace-content" tabIndex={-1}>
        <div className="workspace-intro">
          <h2>{PAGES[page].label}</h2>
          <p>{PAGES[page].description}</p>
        </div>
        {PAGES[page].element}
      </div>
    </div>
  );
}
