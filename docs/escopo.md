# Escopo do sistema — rastreabilidade ementa → módulo → teste

> Status: **rascunho da Fase 0, aguardando aprovação do usuário.**
> Este documento mapeia cada tópico das três ementas para os módulos do sistema e para os testes de referência que comprovam a cobertura. Também registra o que o sistema faz **além** das ementas.

## 1. Convenções de identificação

| Prefixo | Significado | Exemplo |
|---|---|---|
| `DM-` | Módulo de projeto (plug-in de topologia, pacote `design/`) | `DM-RET1` |
| `BD-` | Bancada de dispositivo isolado (pacote `devices/`) | `BD-DIODO` |
| `BV-` | Bancada virtual de ensaio (reproduz ensaio de laboratório) | `BV-AMPOP` |
| `SV-` | Serviço transversal (simulador, seleção, térmico, magnéticos, relatórios) | `SV-TERM` |
| `GT-` | *Golden test*: caso resolvido de livro-texto ou nota de aplicação | `GT-RET1-01` |
| `AS-` | Teste analítico × simulação ngspice | `AS-RET1-01` |
| `DS-` | Teste modelo de dispositivo × pontos digitalizados do datasheet | `DS-1N4007-IV` |
| `PT-` | Teste de propriedade (Hypothesis) | `PT-ENERGIA` |

**Sobre as referências dos *golden tests*:** a coluna "Fonte do caso de referência" indica livro e capítulo/assunto. O número exato do exemplo, da página e da edição **será confirmado com o livro em mãos** antes de o teste ser escrito (regra 1: não inventar). Exemplos indicados pelo usuário a partir das listas de exercícios usadas em aula têm prioridade.

## 2. Módulos do sistema

### 2.1 Serviços transversais

| ID | Módulo | Responsabilidade |
|---|---|---|
| `SV-CORE` | `core/` | Unidades (`pint`), notação de engenharia, séries E (E6–E192), erros, utilidades numéricas |
| `SV-COMP` | `components/` | Banco de componentes, esquemas por categoria, busca facetada, rastreabilidade, revisão |
| `SV-SEL` | `selection/` | Derating, filtragem, ranqueamento, seleção manual e travamento |
| `SV-TERM` | `thermal/` | Rede térmica Rθjc–Rθcs–Rθsa, acoplamento eletrotérmico, seleção de dissipador; Zθ(t) em fase posterior |
| `SV-MAG` | `magnetics/` | Projeto de indutores e transformadores (Ap/Kg), catálogo de núcleos, fios, perdas, ΔT |
| `SV-SIM` | `simulation/` | Modelo interno de circuito, netlist, ngspice, pós-processamento (média, RMS, FFT, THD, potências) |
| `SV-SCH` | `schematic/` | Esquemático automático (gabarito por topologia), símbolos IEC/ANSI, exportação SVG/PDF/PNG/netlist |
| `SV-REP` | `reports/` | Memória de cálculo, BOM, relatório PDF/HTML, modo didático |
| `SV-LAB` | `reports/lab/` | Roteiro de prática de laboratório gerado a partir do projeto |
| `SV-PDF` | `datasheets/` | Extração de PDF, OCR, LLM opcional, digitalização de curvas, ajuste de modelo SPICE |
| `SV-EDIT` | front-end | Simulador livre: editor de esquemático, pontas de prova, análises, visualizador de sinais |

### 2.2 Bancadas de dispositivos

| ID | Dispositivos | Curvas e análises |
|---|---|---|
| `BD-PN` | Junção PN (física) | Depleção × tensão reversa, dopagem, temperatura, equação de Shockley, ni(T) |
| `BD-DIODO` | Retificador, rápido, ultrarrápido, Schottky, SiC | I-V direta/reversa, efeito de Tj, recuperação reversa (trr, Qrr) |
| `BD-ZENER` | Zener, referências, TVS | Curva, regulação, rz, coeficiente de temperatura |
| `BD-2T` | LED, fotodiodo, varicap, túnel, PIN, varistor, DIAC | Curvas características específicas por tipo |
| `BD-TBJ` | TBJ de sinal e de potência | Entrada, saída, hFE × IC, reta de carga, SOA, região de operação |
| `BD-FET` | JFET, MOSFET (Si, SiC, GaN) | Transferência, saída, RDS(on) × Tj, Qg, capacitâncias |
| `BD-IGBT` | IGBT e módulos | VCE(sat) × IC, Eon/Eoff |
| `BD-TIR` | SCR, TRIAC, DIAC, GTO | Curva, IGT, IH, IL, quadrantes de disparo |
| `BD-AMPOP` | Ampop, comparador | Malha aberta (A(f)), slew rate, excursão |
| `BD-REG` | Reguladores lineares | Dropout, regulação de linha/carga, dissipação |

### 2.3 Módulos de projeto (plug-ins)

| ID | Família | Seção do prompt |
|---|---|---|
| `DM-RET1` | Retificadores monofásicos não controlados + filtros C, LC, π + transformador | 3.1 |
| `DM-RETC1` | Retificadores monofásicos controlados e semicontrolados (R, RL, RLE, roda livre) | 3.1 |
| `DM-RET3` | Retificadores trifásicos 3, 6 e 12 pulsos, não controlados e controlados, comutação (μ) | 3.1 |
| `DM-FORMA` | Ceifadores, grampeadores, dobradores e multiplicadores | 3.1 |
| `DM-ZEN` | Regulador Zener (com e sem transistor) | 3.2 |
| `DM-LIN` | Reguladores série, com ampop, foldback, 78xx/79xx, LM317/337, LDO, fontes simétricas | 3.2 |
| `DM-BIAS` | Polarização TBJ/FET, estabilidade térmica, retas de carga | 3.5 |
| `DM-SSA` | Amplificadores de pequenos sinais (EC, BC, CC, FC, DC, GC, Darlington, multiestágio, resposta em frequência) | 3.5 |
| `DM-DIFF` | Par diferencial, espelhos e fontes de corrente, CMRR | 3.5 |
| `DM-PA` | Amplificadores de potência/áudio classes A, B, AB, D; integrados de áudio | 3.5 |
| `DM-CHAVE` | Chaves transistorizadas (TBJ/MOSFET em corte/saturação) | 3.5 |
| `DM-OPA` | Ampops lineares (inversor, não inversor, somador, integrador, instrumentação, I-V, V-I) | 3.6 |
| `DM-OPNL` | Ampops não lineares (comparador, Schmitt, retificador de precisão, log, limitador) | 3.6 |
| `DM-FIL` | Filtros passivos e ativos, síntese Butterworth/Chebyshev/Bessel/elíptico | 3.7 |
| `DM-OSC` | Osciladores, multivibradores, temporizadores, 555, geradores de função | 3.6, 3.9 |
| `DM-INST` | Medidores V/I/P, 4–20 mA, amplificadores de corrente, condicionamento de sensores | 3.8 |
| `DM-CC` | Conversores CC-CC não isolados (buck, boost, buck-boost, Ćuk, SEPIC, Zeta) + malha de controle | 3.3 |
| `DM-CCI` | Conversores CC-CC isolados (flyback, forward, push-pull, meia ponte, ponte completa) | 3.3 |
| `DM-INV` | Inversores monofásicos e trifásicos, modulações, filtro LC, tempo morto | 3.4 |
| `DM-CACA` | Gradadores (controle de fase e ciclo integral), disparo com DIAC | 3.4 |
| `DM-CMD` | Disparo de tiristores, gate drivers, bootstrap, isolação, snubbers, fusíveis/I²t, varistores, NTC | 3.4, 3.9 |

## 3. Matriz de rastreabilidade

### 3.1 Dispositivos Eletrônicos (5º período, 72 h/a)

| Tópico da ementa | Módulos | Testes de referência | Fonte do caso de referência |
|---|---|---|---|
| Física e propriedades dos semicondutores | `BD-PN` | `GT-PN-01` (largura de depleção × VR), `GT-PN-02` (ni × T), `PT-PN-MONOT` (depleção cresce com VR) | Sedra & Smith, cap. de semicondutores; Boylestad, cap. 1 |
| Junção PN; características e aplicações do diodo | `BD-DIODO`, `DM-RET1`, `DM-FORMA` | `GT-DIODO-01` (Shockley, ponto de operação), `DS-1N4007-IV`, `GT-RET1-01..03`, `GT-FORMA-01..03` (ceifador, grampeador, dobrador) | Boylestad, cap. 1–2; Malvino, cap. de diodos |
| Diodo Zener: características e aplicações | `BD-ZENER`, `DM-ZEN` | `GT-ZEN-01..03` (regulação com variação de linha e carga, faixa de RL), `AS-ZEN-01` | Boylestad, cap. 2; Malvino, cap. de Zener |
| Outros semicondutores de dois terminais | `BD-2T`, `BD-ZENER` | `DS-<peça>-*` por dispositivo (LED, Schottky, varicap); `GT-2T-01` (polarização de LED) | Boylestad, cap. de dispositivos de dois terminais |
| TBJ e FET: construção, funcionamento, características | `BD-TBJ`, `BD-FET` | `DS-BC547-OUT`, `DS-2N3904-HFE`, `DS-IRFZ44N-TRANSF` | Boylestad, cap. 3 e 6; Sedra & Smith |
| TBJ e FET: polarização | `DM-BIAS` | `GT-BIAS-01..03` (polarização fixa, divisor, realimentação de coletor), `GT-BIAS-FET-01..03` (autopolarização, divisor, MOSFET de enriquecimento), `AS-BIAS-01` (.OP × analítico) | Boylestad, cap. 4 e 7 |
| TBJ e FET: aplicações (amplificadores, chaves) | `DM-SSA`, `DM-CHAVE` | `GT-SSA-01..03` (EC com re, CC, BC), `GT-SSA-FET-01..03`, `AS-SSA-01` (ganho .AC × analítico), `GT-CHAVE-01` | Boylestad, cap. 5 e 8; Malvino |
| Projetos e simulações | Assistente + `SV-SIM`, `SV-LAB` | `E2E-DISP-01` (Playwright: projeto de retificador do início ao relatório) | — |

### 3.2 Eletrônica (6º período, 72 h/a)

| Tópico da ementa | Módulos | Testes de referência | Fonte do caso de referência |
|---|---|---|---|
| Amplificador diferencial | `DM-DIFF` | `GT-DIFF-01..03` (ganho diferencial, modo comum, CMRR, espelho de corrente), `AS-DIFF-01` | Boylestad, cap. de amplificadores diferenciais; Sedra & Smith; Razavi |
| Ampop ideal e real; características; modos; circuitos básicos; malha aberta e fechada | `DM-OPA`, `BD-AMPOP` | `GT-OPA-01..03` (inversor, não inversor, somador), `AS-OPA-01` (banda passante com GBW real), `PT-OPA-GBW` (ganho × banda constante) | Pertence; Boylestad, cap. de ampops; Sedra & Smith |
| Determinação de características de ampops | `BV-AMPOP` | `BV-AMPOP-OFFSET`, `-IB`, `-GBW`, `-SR`, `-CMRR`, `-PSRR`, `-EXCURSAO`: cada ensaio simulado deve recuperar o parâmetro do modelo do banco dentro da tolerância | Pertence (ensaios); datasheets LM741, TL071 |
| Amplificadores multiestágio; amplificadores de potência | `DM-SSA`, `DM-PA` | `GT-SSA-MULT-01..02`, `GT-PA-01..03` (classe A, B, AB: Pout, η, PD por transistor), `AS-PA-01` (THD classe B × AB) | Boylestad, cap. de amplificadores de potência; Malvino |
| Filtros ativos | `DM-FIL` | `GT-FIL-01..03` (Sallen-Key PB Butterworth 2ª ordem, MFB PF, Chebyshev 4ª ordem), `AS-FIL-01` (fc .AC × projeto), `PT-FIL-E24` (arredondamento E24 → desvio de fc reportado) | Pertence; Horowitz & Hill |
| Geradores de sinais; osciladores; multivibradores; temporizadores | `DM-OSC` | `GT-OSC-01..03` (Wien, deslocamento de fase, 555 astável), `AS-OSC-01` (frequência .TRAN × analítica), `GT-OSC-MV-01` (astável com TBJ) | Boylestad; Pertence; datasheet NE555 |
| Fontes de alimentação reguladas | `DM-ZEN`, `DM-LIN` | `GT-LIN-01..03` (série com TBJ, LM317 ajustável, 7805 com dissipador), `AS-LIN-01` (regulação de linha), `PT-LIN-PD` (PD = (Vin − Vout)·Io + Vin·Iq) | Boylestad, cap. de fontes; Malvino; datasheet LM317 |
| Aplicações lineares e não lineares com ampops | `DM-OPA`, `DM-OPNL` | `GT-OPNL-01..03` (Schmitt: limiares, retificador de precisão, logarítmico), `AS-OPNL-01` | Pertence; Sedra & Smith |
| Projetos e simulações | Assistente, `SV-SIM`, `SV-LAB` | `E2E-ELET-01` (filtro ativo do início ao roteiro de prática) | — |

### 3.3 Eletrônica de Potência (7º período, 90 h/a)

| Tópico da ementa | Módulos | Testes de referência | Fonte do caso de referência |
|---|---|---|---|
| Fundamentos e aplicações; circuitos a tiristores | `BD-TIR`, `BD-FET`, `BD-IGBT`, `DM-CMD` | `DS-TIC106-*`, `DS-BT136-*`, `GT-CMD-01` (disparo RC-DIAC), `GT-CMD-02` (UJT) | Rashid, cap. de tiristores; Ahmed |
| Conversores CA/CC não controlados e controlados; parâmetros de desempenho | `DM-RET1`, `DM-RETC1`, `DM-RET3` | `GT-RET1-01..03`, `GT-RETC1-01..03` (carga R, RL, RLE), `GT-RET3-01..03` (6 pulsos, controlado, com μ), `AS-RET-01..03` (Vmed, Vrms, FP, THD .TRAN × analítico), `PT-RET-FP` (FP ≤ 1) | Hart, cap. 3–4; Rashid, cap. de retificadores; Barbi |
| Conversores CC/CC | `DM-CC`, `DM-CCI`, `SV-MAG` | `GT-CC-01..03` (buck, boost, buck-boost em MCC), `GT-CC-MCD-01`, `GT-CCI-01..02` (flyback, forward), `AS-CC-01` (ripple de buck), `PT-ENERGIA` (Pin = Pout + perdas), `PT-CC-D` (0 < D < 1) | Hart, cap. 6–7; Erickson & Maksimović; Mohan; Barbi |
| Conversores CC/CA (onda quadrada e PWM) | `DM-INV` | `GT-INV-01..03` (onda quadrada, SPWM bipolar, unipolar: harmônicos), `AS-INV-01` (THD .TRAN × analítico), `PT-INV-MA` (fundamental ∝ ma na região linear) | Hart, cap. 8; Mohan; Rashid |
| Harmônicos e filtros | `SV-SIM` (FFT/THD), `DM-INV`, `DM-RET*`, `DM-FIL` | `GT-HARM-01` (série de Fourier de onda quadrada), `PT-FFT-PARSEVAL` (energia tempo = frequência), `GT-INV-FLT-01` (filtro LC de saída) | Hart, cap. 2 (potência e harmônicos); Mohan |
| Proteção de dispositivos e circuitos de comando | `DM-CMD`, `SV-TERM` | `GT-CMD-SNUB-01` (snubber RC), `GT-TERM-01..03` (Tj com dissipador), `GT-CMD-I2T-01` (fusível × I²t do SCR), `GT-CMD-BOOT-01` (capacitor de bootstrap IR2110) | Mohan, cap. de snubbers e projeto térmico; Rashid; notas de aplicação International Rectifier/Infineon |
| Projetos, simulações e práticas com diodos e tiristores | Assistente, `SV-SIM`, `SV-LAB`, `DM-CACA` | `GT-CACA-01..02` (gradador com carga R e RL), `E2E-POT-01` (retificador controlado do início ao roteiro de prática) | Hart; Rashid |

## 4. Além das ementas

O que o sistema entrega e as ementas não pedem explicitamente:

- **Seleção de componentes reais com derating** e rastreabilidade de cada parâmetro até a página do datasheet (`SV-COMP`, `SV-SEL`).
- **Painel de limites de operação**: curvas "grandeza crítica × potência de carga", controles deslizantes de carga, tensão de entrada e temperatura.
- **Modelo térmico** e seleção de dissipador; acoplamento eletrotérmico iterativo.
- **Projeto de magnéticos** completo (núcleo real de catálogo, espiras, entreferro, bitola com efeito pelicular, perdas, ΔT).
- **Malha de controle** de conversores CC-CC (modelo médio, compensadores tipo II/III, margens).
- **Conversores isolados**, **SVPWM**, **12 pulsos**, **classe D**, **Ćuk/SEPIC/Zeta**, **GaN e SiC**.
- **Instrumentação industrial**: 4–20 mA (2 e 3 fios, compliance), shunt, Hall, TC, RMS verdadeiro, condicionamento de ponte, termopar, RTD, termistor.
- **Monte Carlo, pior caso e varredura de temperatura** com tolerâncias do datasheet.
- **Importação de datasheets em PDF** com LLM opcional, digitalização de curvas e ajuste de modelo SPICE.
- **Roteiro de prática de laboratório** gerado a partir de cada projeto (atende às 18 h/a práticas das três disciplinas).
- **Relatórios** com memória de cálculo em LaTeX, BOM com margens e esquemático exportável.

## 5. Fora do escopo (nesta versão)

- Layout de placa de circuito impresso (apenas exportação de esquemático/netlist para KiCad na Fase 9, se viável).
- Simulação eletromagnética de campo (FEM) de magnéticos; usamos modelos analíticos (Steinmetz, Dowell).
- Integração com APIs de distribuidores para preço e estoque em tempo real (campo de custo é manual).
- Simulação digital/lógica além do necessário para PWM, comparadores e 555.
- Certificação normativa (EMC, segurança elétrica); o sistema pode indicar limites de norma como informação, mas não certifica.

## 6. Critério de "tópico coberto"

Um tópico da ementa só é marcado como coberto em `docs/roadmap.md` quando:
1. o módulo correspondente existe e passa pelos critérios de aceite gerais (seção 13 do prompt);
2. todos os testes `GT-`, `AS-` e `DS-` listados acima passam dentro da tolerância documentada;
3. existe `docs/validacao/<modulo>.md` revisado pelo usuário.
