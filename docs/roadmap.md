# Roadmap

Legenda: ✅ concluído · 🔄 em andamento · 👀 aguardando revisão do usuário · ⏳ não iniciado · 🔶 parcial, bloqueado por decisão ou acesso · ➡️ movido para outra fase

| Fase | Entrega | Status |
|---|---|---|
| 0 | Descoberta e planejamento | ✅ |
| 1 | Fundação | ✅ |
| 2 | Banco de componentes e bancada de dispositivos | ✅ |
| 3 | Retificadores (vertical completa, define o padrão) | 👀 |
| 4 | Fontes reguladas e amplificadores | ✅ |
| 5 | Ampops, filtros e instrumentação | ✅ |
| 6 | Eletrônica de potência chaveada | 👀 |
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

## Fase 4 — Fontes reguladas e amplificadores ✅ (aprovada em 2026-11-14)

- ✅ `DM-ZEN`, `DM-LIN`, `DM-BIAS`, `DM-SSA`, `DM-DIFF`, `DM-PA`, `DM-PAD` (classe D), `DM-CHAVE`, `DM-FORMA`
- ✅ Acréscimo: LDO no `DM-LIN`, JFET no `DM-BIAS` e `DM-SSA`, Darlington no `DM-PA` e `DM-CHAVE`
- ✅ Modelos de dispositivo comuns ao cálculo e ao ngspice (Ebers-Moll, MOSFET quadrático, Zener linear por partes); ponto Q exato; resposta em frequência nodal exata, conferida com `.ac`
- ✅ Catálogo de reguladores (MC78xx, MC79xx, LM317, LM337; LDO NCP1117 e LM2931) com esquemas `regulator.*`; JFETs 2N5457, 2N5458 e MPF102 (`jfet.n`)
- ✅ Aba **Projeto**: diagrama de Bode (cálculo × `.ac`), eixo de tempo por módulo, campos por variante
- ✅ `AS-*` da Fase 4 (44 casos, maior erro 0,60 % nas grandezas exatas)
- 🔶 `GT-P8..P19`: casos propostos, aguardando conferência do usuário
- ✅ [validacao/fontes-amplificadores.md](validacao/fontes-amplificadores.md), [validacao/catalogo-reguladores.md](validacao/catalogo-reguladores.md), [validacao/catalogo-jfet.md](validacao/catalogo-jfet.md)

## Fase 5 — Ampops, filtros e instrumentação ✅ (aprovada em 2026-11-15)

- ✅ `DM-OPA` (10 configurações), `DM-FIL` (Butterworth, Chebyshev, Bessel, elíptico; Sallen-Key, MFB, KHN, escada LC), `DM-OPNL`, `DM-OSC` (Wien, deslocamento de fase, astável, 555, multivibrador com TBJ), `DM-INST`
- ✅ `BD-AMPOP` e `BV-AMPOP-*` (VOS, IB, IOS, A0, CMRR, PSRR, GBW, SR, excursão)
- ✅ Macromodelo de ampop comum ao cálculo e ao ngspice; análise nodal exata com polos; integração Gear nos transitórios com ampop
- ✅ Catálogo: LM741C, LM358, TL071C (`opamp`), LM311 (`comparator`), NE555 (`timer`)
- ✅ `AS-*` da Fase 5 (70 casos, 175 grandezas, maior erro 2,19 % na amplitude do oscilador de deslocamento de fase, tol. 5 %)
- ✅ `PT-OPA-GBW`, `PT-FIL-E24`
- 🔶 `GT-P20..P32`: casos propostos, aguardando conferência do usuário
- ✅ [validacao/ampops-filtros-instrumentacao.md](validacao/ampops-filtros-instrumentacao.md), [validacao/catalogo-ampops.md](validacao/catalogo-ampops.md)

## Fase 6 — Eletrônica de potência chaveada ✅ (aprovada em 2026-11-15)

- ✅ `SV-MAG`: indutores, flyback e transformadores em núcleos do catálogo (Ap, entreferro, janela, Steinmetz, ΔT)
- ✅ `DM-CC` (buck, boost, buck-boost, Ćuk, SEPIC, Zeta; MCC e MCD; malha tipo II/III pelo fator K)
- ✅ `DM-CCI` (flyback, forward, push-pull, meia ponte, ponte completa)
- ✅ `DM-INV` (mono e trifásico; onda quadrada, quase quadrada, SPWM bipolar e unipolar, SVPWM; tempo morto; filtro LC amortecido)
- ✅ `DM-CACA` (controle de fase R e RL, ciclos inteiros, rede RC + DIAC)
- ✅ `DM-CMD` (R_g, bootstrap AN-978, snubber RCD, fusível I²t, varistor, NTC)
- ✅ Bancada `BD-IGBT`
- ✅ Catálogo: IRF840, FGH40N60SMD, MBR20100CT, MUR1560, IR2110; núcleos E/ETD Ferroxcube, 3C94/3C96, carretéis Thornton
- ✅ `AS-*` da Fase 6 (33 casos, 114 grandezas, maior erro 3,68 % na THD da corrente do inversor filtrado com mf = 201, tol. 10 %)
- ✅ `PT-ENERGIA`, `PT-CC-D`, `PT-INV-MA`, `PT-FFT-PARSEVAL`
- 🔶 `GT-P33..P49`: casos propostos, aguardando conferência do usuário
- ➡️ `GT-CMD-02` (UJT): sem UJT no catálogo
- ✅ [validacao/potencia-chaveada.md](validacao/potencia-chaveada.md), [validacao/magneticos.md](validacao/magneticos.md), [validacao/catalogo-potencia.md](validacao/catalogo-potencia.md)

## Fase 7 — Simulador livre ✅ (aprovada em 2026-11-15)

- ✅ Editor de esquemático (35 símbolos, peças do catálogo, rótulos, pontas V, V diferencial, I e P)
- ✅ Análises .OP, .TRAN, .AC, .DC, ruído; .STEP paramétrico e de temperatura
- ✅ Monte Carlo e pior caso com tolerâncias do componente e faixas do datasheet (V_Z, h_FE, V_GS(th))
- ✅ Osciloscópio (dois eixos, cursores, zoom), medidas, Bode, FFT/THD, expressões, XY, estatística
- ✅ Importação e exportação de netlist SPICE; CSV e figuras SVG/PNG/PDF (Matplotlib)
- ✅ `AS-SIM-01..06`, `PT-SIM`, E2E no navegador (`scripts/e2e.sh`)
- ✅ [validacao/simulador.md](validacao/simulador.md)

## Fase 8 — Importação de datasheets ✅ (aprovada em 2026-11-15)

- ✅ `SV-PDF`: upload com SHA-256, extração em linhas visuais, OCR (Tesseract via PyMuPDF)
- ✅ Mapeamento por regras com página, trecho e posição na página; ranking de categoria
- ✅ LLM opcional (D9) com verificação do trecho e dos números no texto do PDF
- ✅ Digitalização de curvas: traço vetorial, seguir cor, cliques; eixos lin/log
- ✅ Importação de `.model`/`.subckt` com carga no ngspice
- ✅ Ajuste de modelo: diodo, TBJ (Gummel-Poon reduzido), MOSFET nível 1; erro simulado no ngspice
- ✅ Tela de importação e revisão com destaque da origem no PDF; abas Curvas e Modelos SPICE
- ✅ `AS-FIT` (4 casos), testes de extração, LLM, digitalização, SPICE e API (57 novos)
- ⏳ `DS-EXT`: comparação com o catálogo nos PDFs reais (rede), aguardando autorização para rodar
- ✅ Ambiente Windows: DLL do ngspice, memória insuficiente classificada
- ✅ [validacao/importacao-datasheets.md](validacao/importacao-datasheets.md)

## Fase 9 — Relatórios, empacotamento e documentação ✅ (aprovada em 2026-11-15)

- ✅ Relatório completo em HTML (imprimível) e PDF: formas de onda (cálculo × ngspice), limites de operação, BOM com margens
- ✅ Lista de materiais com esforço × nominal × margem, Tj, dissipador, datasheet, custo; CSV, XLSX e PDF
- ✅ Projetos: salvar, abrir, duplicar, revisões e restauração; arquivo aberto `.circuito.json`
- ✅ Exportação KiCad (netlist `.net`) do projeto e do simulador; ➡️ `.kicad_sch` fora do escopo
- ✅ Pacote para Windows (PyInstaller, com ngspice e catálogo) e `LEIA-ME.txt`
- ✅ [Manual do usuário](manual/README.md) e [guia de extensão](guia-extensao.md)
- ✅ [validacao/relatorios-empacotamento.md](validacao/relatorios-empacotamento.md)

## Fase 10 — Vista de protoboard ✅ (aprovada em 2026-11-16; pedido em 2026-11-15, decisão D11)

- ✅ Simbologia real (encapsulamento desenhado em SVG) ao lado do símbolo 2D, no simulador e no catálogo
- ✅ Pinagem por peça no catálogo, com fonte no datasheet e status de revisão (13 registros, 74 peças)
- ✅ Protoboard de 830 pontos com barramentos e montagem manual no simulador
- ✅ Montagem automática e roteiro de montagem passo a passo
- ✅ Montagem gerada a partir do assistente de projeto (19 de 22 módulos)
- ✅ Conferência protoboard × esquemático (faltando, sobrando, trocada, não montado, furo em conflito)

## Fase 11 ✅ Microcontroladores, CLP e instrumentação (aprovada em 2026-11-16; decisão D12)

- ✅ Datasheets de instrumentação, CLP e sensores de corrente, tensão e energia na fila (grupos 26 a 39)
- ⏳ Esquema de categoria para sensor, transmissor, atuador, microcontrolador e CLP (sensores da co-simulação ainda fora do catálogo)
- ✅ ESP32 e Arduino: programa estilo Arduino interpretado e co-simulado com o ngspice (ADC, GPIO, PWM, DAC, Serial)
- ✅ CLP: ladder e texto estruturado em ciclo de varredura, E/S 24 V, 4 a 20 mA e 0 a 10 V ligadas ao circuito
- ✅ Modelos de sensor com valores do datasheet: LM35, Pt100 (IEC 60751), ACS712, transmissor 4 a 20 mA; termopar J, K, T, E e N (NIST ITS-90, conferido nas tabelas Omega), em 2026-11-16; ⏳ ZMPT101B, SCT-013 (sem PDF)
- ✅ Exemplos: medidor de energia com ESP32; controle PWM com Arduino; laço de 4 a 20 mA no CLP; ESP32 e CLP integrados
- ✅ Modelos de acionamento (2026-11-16): motor de indução (αβ), inversor V/f com rampas e SPWM, soft-starter (rampa de tensão e limitação de corrente), contator, motor de passo com driver STEP/DIR; `AS-DRV-01..06`; validação em [validacao/acionamentos-termopar.md](validacao/acionamentos-termopar.md)
- ✅ Exemplo integrado de bombeamento com pressão constante (CLP + inversor + bomba + ESP32); partida direta × soft-starter pelo CLP e posicionamento com motor de passo pelo Arduino (2026-11-16)
- ✅ Editor de programa com diagrama ladder, monitor serial, protoboard dos exemplos
- Validação: `docs/validacao/microcontroladores-clp.md`; manual: `docs/manual/08-microcontroladores-clp.md`

## Fase 12 ✅ Catálogo de dispositivos reais: instrumentação, automação, passivos (aprovada em 2026-11-16; decisão D13)

- ✅ Busca dos datasheets que faltavam (3 rodadas; manuais e catálogos quando não há datasheet): 457 de 510 itens com PDF
- ✅ Atributos em texto no registro; 53 esquemas de categoria novos (77 no total)
- ✅ Transcrição dos PDFs em registros com página e trecho: 393 registros novos (758 no catálogo), rascunho a revisar
- ⏳ 53 itens sem PDF (portais que exigem navegador) e 17 com PDF sem dados da peça
- ✅ Peças reais nos símbolos da co-simulação (LM35, Pt100, ACS712, potenciômetro, relé, placas, CLP)
- Validação: `docs/validacao/catalogo-dispositivos.md`

## Correções numéricas — 2026-11-16

- Limitador com Zener (`DM-OPNL`): distribuição equilibrada da resistência do ramo na netlist,
  preservando o limiar e a resistência total, para resolver a falha de convergência no Windows.
- `PT-INV-MA`: grade do teste refinada com limite explícito para o erro das bordas PWM;
  caso `ma = 0,5664`, `mf = 51`, bipolar fixado como regressão. Tolerâncias mantidas.
- Validação: 959 testes aprovados entre as rodadas, 1 pulado; cobertura unitária de 90,83 %.
  Suíte integral ainda pendente: teste do motor de passo excedeu o tempo de execução;
  ele e o exemplo integrado correspondente ficaram fora da validação concluída.
- Evidências e resultados: [validacao/correcoes-numericas.md](validacao/correcoes-numericas.md).

## Interface assistida — primeira entrega aprovada (2026-11-17)

- Referência escolhida pelo usuário: segunda proposta, **Bancada assistida**, inspirada na
  organização visual do STM32CubeProgrammer.
- Navegação superior com ícones e nomes, estado do simulador e descrição de cada área.
- Simulador como tela inicial; fluxo **Circuito → Configurar análise → Resultados**.
- Biblioteca recolhível, ferramentas de desenho sempre acessíveis e seleção de componentes
  pelo desenho ou pela lista no painel de propriedades.
- Tema claro/escuro, adaptação a telas menores e navegação por teclado.
- Manual: [manual/04-simulador.md](manual/04-simulador.md).
- Validação e limites: [validacao/interface-assistida.md](validacao/interface-assistida.md).
- Testada pelo usuário e aprovada para envio ao GitHub. Próximo passo: estender o fluxo assistido ao projeto guiado.


- Ajuste da interface assistida: opção de nomes reais dos nós e resultados limitados às probes
  da execução e expressões explícitas; detalhes em `validacao/interface-assistida.md`.

## Análise de Projetos com grandezas da simulação — aguardando revisão (2026-11-20)

- Seletor renomeado para "Circuito"; tensões de entrada indicadas como eficazes.
- DM-RET1, DM-RETC1 e DM-RET3 partem da tensão eficaz do secundário e da potência da carga (sai a
  tensão média desejada).
- Resultados medidos no ngspice: pico, médio e eficaz de tensões e correntes; S, P, Q, D, FP e cos φ₁.
- Formas de onda de primário, secundário, carga e dispositivos, com linhas de médio/eficaz e ponto de
  pico; sondas por clique no esquemático (tensão no nó, diferencial, corrente, potência).
- Edição de valores e troca de modelo pelo esquemático.
- Detalhes e limitações: [validacao/analise-projetos.md](validacao/analise-projetos.md).

## Bancada virtual e edição de projetos — aprovada pelo usuário (2026-11-17)

- Navegação renomeada: Biblioteca, Análise de dispositivos e Análise de Projetos.
- Duas protoboards, barra vertical independente, zoom inicial de 100% e inserção completa de peças.
- Fontes de tensão/corrente agrupadas com controles CC, senoidal, quadrada e triangular.
- Fonte de bancada de três canais e leituras de corrente obtidas da simulação.
- Seletor Adicionar instrumento (fonte, gerador e osciloscópio), inserção completa e remoção pelo painel.
- Osciloscópio didático de 2/4 canais com ponteiras, escalas, acoplamento, Autoset e trigger.
- Circuito editável nas revisões dos projetos, Salvar como e envio às duas vistas do Simulador.
- Detalhes, critérios de validação e limitações: [validacao/bancada-virtual.md](validacao/bancada-virtual.md).

## Protoboard realista, placas encaixáveis e zoom — aguardando revisão (2026-11-19)

- Arduino Uno e ESP32-DevKitC com as duas barras de pinos, encaixados sobre a canaleta pelo pino 1.
- Desenhos próprios para sensores, transmissores (novo transmissor 4-20 mA para RTD a 3 fios),
  termopar, ACS712, motores, soft-starter, inversor, contator, driver, relé, aquecedor e botão.
- Sentido de giro dos motores após a simulação; zoom de 50 a 250 % na protoboard e controles de zoom
  no esquemático; "fonte comportamental" renomeada para "fonte dependente".
- Detalhes e limitações: [validacao/protoboard-realista.md](validacao/protoboard-realista.md).

## Melhorias do simulador, esquemático 2D e protoboard — aguardando revisão (2026-11-20)

- Telas maiores e tela cheia. Terra no grupo Fontes. Girar (R) e espelhar (M) antes de inserir.
- Copiar e colar, seleção por retângulo e botão de ligar pinos alinhados.
- LEDs Vishay de seis cores e lâmpadas de 12/24/230 V (OSRAM e LEDVANCE) mais lâmpadas de placa
  de 127/220 V, todos acendendo conforme a corrente simulada.
- Chaves tácteis NA, NF e de 4 terminais. Transformadores monofásico e trifásico (Y/Δ) definidos
  pelos dados de placa.
- 10 motores CC FAULHABER no catálogo (`motor.dc`).
- Homologação das peças do circuito na Análise de Projetos.
- Protoboard: montagem automática com menos fios e botões para retirar peças.
- Revisão: montagem automática na placa de baixo (perto dos instrumentos), sem peças sobrepostas,
  fios sem cruzar nem passar sobre peças, alimentação pelos barramentos; fonte de vários canais
  num só painel; "Limpar circuito" no esquemático; "Ponta" passa a "Ponteira".
- Detalhes, fontes e limitações: [validacao/simulador-melhorias.md](validacao/simulador-melhorias.md).

## Queima de componentes na simulação — aguardando revisão (2026-11-20)

- Após a simulação, tensão, corrente, potência e temperatura de junção de cada peça são
  comparadas com os limites do datasheet (ou informados no resistor e no capacitor genéricos).
- Peça acima do limite aparece como QUEIMOU no esquemático e QUEIMADO na protoboard, com uma
  caixa de alerta (motivo, o que fazer e de onde vem o limite).
- Detalhes e limitações: [validacao/queima-componentes.md](validacao/queima-componentes.md).

