# Roadmap

Legenda: ✅ concluído · 🔄 em andamento · 👀 aguardando revisão do usuário · ⏳ não iniciado

| Fase | Entrega | Status |
|---|---|---|
| 0 | Descoberta e planejamento | ✅ |
| 1 | Fundação | ✅ |
| 2 | Banco de componentes e bancada de dispositivos | 🔄 |
| 3 | Retificadores (vertical completa, define o padrão) | ⏳ |
| 4 | Fontes reguladas e amplificadores | ⏳ |
| 5 | Ampops, filtros e instrumentação | ⏳ |
| 6 | Eletrônica de potência chaveada | ⏳ |
| 7 | Simulador livre e editor de esquemáticos | ⏳ |
| 8 | Importação de datasheets em PDF | ⏳ |
| 9 | Relatórios, empacotamento e documentação | ⏳ |

---

## Fase 0 — Descoberta e planejamento ✅

- ✅ `docs/escopo.md` com matriz ementa → módulo → teste
- ✅ `docs/arquitetura.md` com diagrama Mermaid e ajustes justificados
- ✅ `docs/modelo-de-dados.md`
- ✅ `docs/roadmap.md`
- ✅ `CLAUDE.md`
- ✅ `docs/decisoes-pendentes.md`
- ✅ Aprovação do usuário de escopo e arquitetura (2026-11-14)

## Fase 1 — Fundação ✅

- ✅ Monorepo `backend/`, `frontend/`, `docs/`, `data/`, `scripts/`
- ✅ Script de verificação local `scripts/check.sh` (D1): ruff, mypy, import-linter, pytest com cobertura, Prettier, tsc, ESLint, Vitest, build
- ✅ Dockerfile e `docker-compose.yml` (não construídos neste ambiente)
- ✅ `core/`: registro de unidades, serialização de grandezas, notação de engenharia, séries E3–E192
- ✅ `CalcStep`, `Calculated[T]` e `CalcLog` (memória de cálculo)
- ✅ Esquema de categoria (diodo retificador) e validação do `ComponentRecord` com regras de rastreabilidade e liberação
- ✅ ngspice via biblioteca compartilhada (ctypes) e via executável (rawfile), com diagnóstico de convergência
- ✅ Simulações em processo separado, com progresso, tempo limite e cancelamento
- ✅ Pós-processamento: média, RMS, pico, pico a pico, potência média, FFT, harmônicos, THD, frequência, razão cíclica e decimação mín./máx.
- ✅ API REST e WebSocket (`/api/v1`)
- ✅ Visualizador de sinais mínimo (uPlot): transitória, CA (módulo/fase) e tabela de ponto de operação
- ✅ `AS-SMOKE-01`: circuitos RC, analítico × ngspice
- ✅ Revisão do usuário ([validacao/fundacao.md](validacao/fundacao.md)), aprovada em 2026-11-14

## Fase 2 — Banco de componentes e bancada 🔄

- ✅ Banco SQLite, importação de YAML, busca facetada, fluxo de revisão (rascunho → em revisão → liberado)
- ✅ Armazenamento de datasheets por SHA-256, download sob demanda, páginas renderizadas
- ✅ Diodos: 28 componentes (retificadores, rápidos, Schottky, sinal), cada valor conferido na página citada (`docs/validacao/catalogo-diodos.md`)
- ⏳ Catálogo: Zener, pontes, TBJ, MOSFET, SCR/TRIAC/DIAC
- ⏳ Dissipadores e núcleos (catálogo a definir)
- ✅ Bancada `BD-DIODO` (curva I×V com temperatura, `AS-DIODO-01`)
- ⏳ Bancadas `BD-PN`, `BD-ZENER`, `BD-TBJ`, `BD-FET`, `BD-TIR`
- ⏳ Sobreposição de curvas digitalizadas do datasheet; testes `DS-*`
- ⏳ `docs/validacao/bancada.md`

## Fase 3 — Retificadores ⏳

- ⏳ `DM-RET1`, `DM-RETC1`, `DM-RET3`, filtros C/LC/π, transformador
- ⏳ `selection/` com derating configurável; `thermal/` estacionário e seleção de dissipador
- ⏳ Painel de limites com controles deslizantes
- ⏳ Esquemático por gabarito, BOM, relatório, roteiro de prática
- ⏳ `GT-RET*`, `AS-RET*`, `PT-RET*`; `docs/validacao/retificadores.md`

## Fase 4 — Fontes reguladas e amplificadores ⏳

- ⏳ `DM-ZEN`, `DM-LIN`, `DM-BIAS`, `DM-SSA`, `DM-DIFF`, `DM-PA`, `DM-CHAVE`, `DM-FORMA`

## Fase 5 — Ampops, filtros e instrumentação ⏳

- ⏳ `DM-OPA`, `DM-OPNL`, `BV-AMPOP`, `DM-FIL`, `DM-OSC`, `DM-INST`, `BD-AMPOP`

## Fase 6 — Eletrônica de potência chaveada ⏳

- ⏳ `DM-CC`, `DM-CCI`, `SV-MAG`, malha de controle; `DM-INV`, `DM-CACA`, `DM-CMD`; `BD-IGBT`

## Fase 7 — Simulador livre ⏳

- ⏳ Editor, pontas de prova, todas as análises, Monte Carlo/pior caso, importação e exportação de netlist

## Fase 8 — Importação de datasheets ⏳

- ⏳ Extração, OCR, LLM opcional, digitalização de curvas, ajuste de modelo SPICE, tela de revisão

## Fase 9 — Relatórios, empacotamento e documentação ⏳

- ⏳ Relatórios completos, exportação KiCad (se viável), instalador, manual, guia de extensão
