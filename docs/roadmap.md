# Roadmap

Legenda: ✅ concluído · 🔄 em andamento · 👀 aguardando revisão do usuário · ⏳ não iniciado

| Fase | Entrega | Status |
|---|---|---|
| 0 | Descoberta e planejamento | ✅ |
| 1 | Fundação | 🔄 |
| 2 | Banco de componentes e bancada de dispositivos | ⏳ |
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

## Fase 1 — Fundação 🔄

- ⏳ Monorepo `backend/`, `frontend/`, `docs/`, `data/`
- ⏳ Script de verificação local `scripts/check.sh` (D1): ruff, mypy, pytest, ESLint, Vitest, import-linter (Linux e Windows)
- ⏳ Docker Compose de desenvolvimento
- ⏳ `core/`: registro de unidades, serialização de grandezas, notação de engenharia, séries E6–E192 (TDD)
- ⏳ `CalcStep` e `Calculated[T]` (memória de cálculo)
- ⏳ Esquemas de categoria e validação do `ComponentRecord`
- ⏳ `NgspiceBackend`: executar netlist e retornar vetores com unidades; worker com cancelamento
- ⏳ Pós-processamento básico: média, RMS, pico, FFT
- ⏳ Visualizador de sinais mínimo (uPlot)
- ⏳ `AS-SMOKE-01`: divisor RC (.OP, .TRAN, .AC) analítico × ngspice

**Critério de saída:** `docker compose up` abre a interface, uma netlist de exemplo simula e os traços aparecem; testes e CI verdes.

## Fase 2 — Banco de componentes e bancada ⏳

- ⏳ CRUD, busca facetada, fluxo de revisão (rascunho → em revisão → liberado)
- ⏳ Catálogo inicial a partir de datasheets oficiais: diodos, Zener, pontes, TBJ, MOSFET, SCR/TRIAC/DIAC (cada parâmetro com página)
- ⏳ Dissipadores e núcleos (catálogo a definir)
- ⏳ Bancadas `BD-PN`, `BD-DIODO`, `BD-ZENER`, `BD-TBJ`, `BD-FET`, `BD-TIR`
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
