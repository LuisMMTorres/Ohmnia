# Roadmap

Legenda: ✅ concluído · 🔄 em andamento · 👀 aguardando revisão do usuário · ⏳ não iniciado · 🔶 parcial, bloqueado por decisão ou acesso · ➡️ movido para outra fase

| Fase | Entrega | Status |
|---|---|---|
| 0 | Descoberta e planejamento | ✅ |
| 1 | Fundação | ✅ |
| 2 | Banco de componentes e bancada de dispositivos | ✅ |
| 3 | Retificadores (vertical completa, define o padrão) | 👀 |
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

## Fase 2 — Banco de componentes e bancada ✅ (aprovada em 2026-11-14)

- ✅ Banco SQLite, importação de YAML, busca facetada, fluxo de revisão (rascunho → em revisão → liberado)
- ✅ Armazenamento de datasheets por SHA-256, download sob demanda, páginas renderizadas
- ✅ Diodos: 28 componentes (retificadores, rápidos, Schottky, sinal), cada valor conferido na página citada (`docs/validacao/catalogo-diodos.md`)
- ✅ Zener e pontes monofásicas: 107 componentes (`docs/validacao/catalogo-zener-pontes.md`)
- ✅ Transistores: 31 TBJ e 2 MOSFET (`docs/validacao/catalogo-transistores.md`)
- ✅ Tiristores: 8 SCR e 6 TRIAC onsemi (`docs/validacao/catalogo-tiristores.md`); esquema de DIAC pronto, sem datasheet acessível
- ✅ Dissipadores: 137 perfis da HS Dissipadores (D8, `docs/validacao/catalogo-dissipadores.md`)
- ➡️ Núcleos magnéticos: passam para a Fase 6 (nenhum dos fabricantes indicados vende núcleos)
- ➡️ DIAC: adiado a pedido do usuário
- ✅ Bancada `BD-DIODO` (curva I×V com temperatura, `AS-DIODO-01`)
- ✅ Bancada `BD-ZENER` (curva reversa, ajuste ao datasheet, `AS-ZENER-01`)
- ✅ Bancadas `BD-TBJ` e `BD-FET` (curvas de saída, ajuste ao datasheet, `AS-TBJ-01`, `AS-FET-01`)
- ✅ Bancada `BD-PN` (ni(T), depleção, campo, Cj, IS; `AS-PN-01`, `GT-PN-02`, `PT-PN-MONOT`)
- ✅ Bancada `BD-TIR` (SCR e TRIAC, quadrantes, IL e IH; `AS-TIR-01`, `AS-TIR-02`)
- ✅ Pontos tabelados do datasheet sobrepostos às curvas; teste `DS-CATALOGO` confere cada valor na página citada
- ➡️ Digitalização de curvas das figuras do datasheet passa para `SV-PDF` (Fase 8)
- ✅ [validacao/bancada.md](validacao/bancada.md)

## Fase 3 — Retificadores 👀

- ✅ `DM-RET1` (meia onda, derivação central, ponte; sem filtro, C, LC, π), `DM-RETC1` (meia onda controlada com e sem roda livre, ponte total e semicontrolada, carga R-L-E), `DM-RET3` (3, 6 e 12 pulsos, comutação por Ls); transformador ideal com relação de espiras e VA
- ✅ `selection/` com derating configurável (critérios didático e industrial), travamento manual de componente, nova seleção sobre a envoltória dos esforços ideal e real
- ✅ `thermal/` estacionário: Tj sem dissipador e Rθsa máxima exigida
- ✅ Escolha automática de dissipador do catálogo, com a correção por ΔT do fabricante
- ✅ Aba **Projeto**: formulário gerado do esquema, controles deslizantes que refazem o projeto (painel de limites), margens, térmico, formas de onda do cálculo × ngspice
- ✅ Esquemático por gabarito (SVG), lista de materiais (CSV), relatório HTML com memória de cálculo (KaTeX embutido, funciona sem internet) e roteiro de prática
- ✅ `AS-RET-01..03` (25 casos, maior erro 0,29 %), `GT-RET*` por fórmulas fechadas, `PT-RET-FP`
- 🔶 `GT-RET-P1..P7`: casos propostos (D6), aguardando conferência do usuário
- ✅ [validacao/retificadores.md](validacao/retificadores.md)

## Fase 4 — Fontes reguladas e amplificadores 👀

- ✅ `DM-ZEN`, `DM-LIN`, `DM-BIAS`, `DM-SSA`, `DM-DIFF`, `DM-PA`, `DM-CHAVE`, `DM-FORMA`
- ✅ Modelos de dispositivo comuns ao cálculo e ao ngspice (Ebers-Moll, MOSFET quadrático, Zener linear por partes); ponto Q exato; resposta em frequência nodal exata, conferida com `.ac`
- ✅ Catálogo de reguladores (MC78xx, MC79xx, LM317, LM337) com esquemas `regulator.*`
- ✅ Aba **Projeto**: diagrama de Bode (cálculo × `.ac`), eixo de tempo por módulo, campos por variante
- ✅ `AS-*` da Fase 4 (32 casos, maior erro 0,60 % nas grandezas exatas)
- 🔶 `GT-P8..P15`: casos propostos, aguardando conferência do usuário
- ✅ [validacao/fontes-amplificadores.md](validacao/fontes-amplificadores.md), [validacao/catalogo-reguladores.md](validacao/catalogo-reguladores.md)

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
