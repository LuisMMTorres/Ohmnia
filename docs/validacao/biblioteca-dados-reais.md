# Biblioteca com dados reais — auditoria e peças novas (2026-11-21)

Pedido do usuário: conferir se os componentes da Biblioteca têm dados reais (não só didáticos),
mantendo os genéricos disponíveis e acrescentando peças reais com datasheet. A placa de ligação
dos transformadores na protoboard é feita em outra conversa.

## 1. Auditoria dos símbolos do Simulador

O catálogo (`data/components/`) só tem peças reais, cada valor com a fonte. O que era didático
eram os **valores padrão dos símbolos** sem peça do catálogo ligada. A tabela mostra, para cada
símbolo que tinha só valores didáticos, o que mudou.

| Símbolo | Antes | Agora |
|---|---|---|
| MOSFET canal P (`pmos`) | só genérico | aceita `mosfet.p` (IRF9540N, BS250): modelo PMOS do datasheet |
| JFET canal P (`pjf`) | só genérico | aceita `jfet.p` (2N5460): modelo PJF do datasheet |
| Transformador monofásico | Vp, Vs, Sn digitados; magnetização e cobre didáticos | aceita `magnetic.transformer`: Hammond 1182L18, 1182M240 (novos) e Triad VPT24-1040; Vp, Vs, Sn e perda no cobre vêm do datasheet |
| Transformador trifásico | idem | aceita `magnetic.transformer_3ph`: BLOCK TT3 1-4-4 e TT3 5-4-4 (novos); perda no cobre = P_sc/Sn |
| Autotransformador | idem | aceita `magnetic.autotransformer`: Hammond 175D-NA e 175F-NA (novos); VH, VX e Sn do datasheet |
| Motor de indução trifásico | R1, X1, R2, X2, Xm, J didáticos | aceita `motor.ac`: WEG W22 16616834, 11567431, 11546979 (novos); polos, f e J do datasheet; circuito equivalente ajustado aos dados de placa |
| Contator tripolar | bobina 5 W, fecha 75 %, abre 40 % (didáticos) | aceita `contactor`: WEG CWM9, CWM12, CWM18, CWM25 (novos); potência da bobina e tensões de fechamento/abertura do catálogo; bobina CA |
| Lâmpada | 9 peças reais (12 V automotivas, 230 V Ledvance) | + Satco S2992 e S2419 (60 W, 120 V, incandescentes A19) |
| Arduino Uno / Nano | limiares e pull-up "didáticos" | limiares 0,3/0,6 VCC e pull-up 20 a 50 kΩ conferidos na tabela DC do ATmega328P (ver §4); resistência de saída de 25 Ω continua didática |

### Continuam didáticos (sem dado de fabricante obtido)

| Item | Motivo | O que falta |
|---|---|---|
| Lâmpadas de 127 V e 220 V "de placa" (só Vn e Pn) | incandescentes de 127 V saíram do mercado brasileiro e nenhum fabricante publica ficha acessível; as 230 V Ledvance e as 120 V Satco cobrem o uso | ficha de uma lâmpada de 127 V, se o usuário tiver |
| Motor de 12 terminais | os datasheets WEG obtidos (folhas de produto) não dizem o número de cabos; o catálogo W22 brasileiro (220/380/440/760 V) não pôde ser lido além da p. 20 | folha de dados de um W22 de 12 cabos |
| Corrente a vazio dos transformadores | nenhuma das fichas a informa | ensaio a vazio ou datasheet com I0 |
| Raspberry Pi Pico (limiares, pull-up, PWM em qualquer GP) | a seção 5.5.3 do datasheet do RP2040 está na p. ~630 do PDF; a leitura pela web corta o texto na p. 21 | o PDF baixado no PC do usuário |
| Arduino Mega (ATmega2560) | datasheet do ATmega2560 não lido | idem |
| Motores FAULHABER 2342 | kE do datasheet é inconsistente com kn e kM (nota já existente nos YAML) | só o fabricante pode corrigir |
| Atrito dos motores, ganho do driver de passo, planta de bombeamento, aquecedor, CLP genérico, soft-starter (tensão inicial), inversor (boost) | são parâmetros da aplicação ou de modelos de comportamento, não de uma peça | — |
| Inversores, soft-starters e driver de passo do catálogo (WEG CFW/SSW, Oriental) | já existem no catálogo, mas os símbolos usam parâmetros de programação (rampas, P0100…), que o usuário define | — |

## 2. Peças novas no catálogo

Todas com `review.status: rascunho` (precisam da sua conferência para entrar na seleção
automática, regra 5) e valores `extraido` com trecho citado. Nenhum PDF pôde ser baixado
(o proxy do ambiente bloqueia os sites dos fabricantes); as fontes foram lidas como texto pela
web, por isso não há SHA-256 e o teste `test_web_values_in_excerpt` confere se cada número
aparece no trecho citado.

| Peça | Fabricante | Fonte (link) | Página |
|---|---|---|---|
| W22 16616834 (3 HP, 6 polos, 230/460 V, cat. B) | WEG | [folha de dados](https://www.wolfautomation.com/content/weg-16616834-three-phase-motor-datasheet.pdf), 08/09/2023 | 1 |
| W22 11567431 (30 HP, 6 polos, 460 V, IE3, cat. N) | WEG | [folha de dados](https://wolfautomation.com/content/weg-w22-11567431-datasheet.pdf), 15/09/2022 | 1 |
| W22 11546979 (60 HP, 4 polos, 230/460 V, cat. B) | WEG | [folha de dados](https://wolfautomation.com/content/weg-w22-11546979-datasheet.pdf), 08/06/2022 | 1 |
| CWM9, CWM12, CWM18, CWM25 | WEG | [catálogo CWM](https://static.weg.net/medias/downloadcenter/hac/hb5/WEG-CWM-50051271-catalogo-pt.pdf) | 24 (bobina), 25 (AC-3) |
| 1182L18 (80 VA), 1182M240 (625 VA) | Hammond | [página da série 1182](https://www.hammfg.com/product/1182) | tabela |
| 175D-NA (500 VA), 175F-NA (1000 VA) | Hammond | [série 175](https://www.mouser.com/datasheet/2/177/175-1390003.pdf), impressão de 8/2/25 | 1 |
| TT3 1-4-4 (1 kVA), TT3 5-4-4 (5 kVA) | BLOCK | [TT3 1-4-4](https://www.block.eu/en_EN/productversion/tt3-1-4-4), [TT3 5-4-4](https://www.block.eu/en_EN/productversion/tt3-5-4-4) | página do produto |
| S2992, S2419 (60 W, 120 V) | Satco | [S2992](https://www.satco.com/catalog/product/specsheets/S2992), [S2419](https://www.satco.com/catalog/product/specsheets/S2419) | spec sheet |

Esquemas: `motor.ac` ganhou polos, I0, I_lr, Tmáx/Tn, escorregamento, J e fator de serviço;
`magnetic.transformer` ganhou I_sec, regulação, P_sc, P0, uk e rendimento; novos
`magnetic.transformer_3ph`, `magnetic.autotransformer` (herdam do transformador) e `contactor`.

### Pontos para a sua conferência

1. **WEG W22**: as colunas de rendimento e fator de potência (25/50/75/100 %) foram associadas
   pela ordem das linhas do texto extraído; confira no PDF. Os datasheets são da linha NEMA
   (EUA), 460 V; não foi possível ler as tabelas do catálogo W22 brasileiro (220/380 V).
2. **WEG CWM**: os dados de bobina valem para o grupo CWM9…CWM25 (60 Hz). A corrente AC-3 é a
   da faixa Ue ≤ 440 V (o catálogo não separa 220 V e 380 V). O código e a revisão do catálogo
   não aparecem no texto lido.
3. **Hammond 1182**: a página da série dá 10,50 % de regulação para o 1182L18; a página da peça,
   11 %. Usei a da série.
4. **BLOCK TT3 1-4-4**: a página dá P_sc = 70 W (ur = 7 %) e uk = 5,1 %, o que é inconsistente
   (uk ≥ ur). Transcrevi como está; o simulador usa P_sc.
5. **Satco S2419**: a ficha dá 240 lm para 60 W (a S2992 dá 595 lm); transcrito como está.

## 3. Circuito equivalente do motor a partir do datasheet

Arquivo: `backend/src/circuitos/machines/induction_fit.py`. O datasheet não dá R1, X1, R2, X2,
Xm; o circuito por fase (Chapman, 5.ª ed., cap. 6) é ajustado por mínimos quadrados a: corrente,
fator de potência e conjugado no ponto nominal, corrente a vazio, corrente de partida e
conjugado máximo. A divisão X1/(X1+X2) vem da IEEE Std 112 pela categoria (B e N: 0,4/0,6).
Perdas no ferro e mecânicas ficam embutidas em R1 e R2.

Resultado para o W22 16616834 a 460 V (ajuste × datasheet):

| Ponto | Datasheet | Circuito | Diferença |
|---|---|---|---|
| Corrente nominal | 4,41 A | 4,28 A | −3 % |
| Fator de potência | 0,70 | 0,76 | +9 % |
| Conjugado nominal | 18,2 N·m | 18,1 N·m | −0,3 % |
| Corrente de partida | 30,9 A | 26,3 A | −15 % |
| Corrente a vazio | 2,75 A | 2,88 A | +5 % |
| Conjugado de partida | 2,0 Tn | 1,29 Tn | −35 % (aviso) |
| Conjugado máximo | 2,8 Tn | 2,95 Tn | +5 % |

**Limitação conhecida:** a gaiola simples não reproduz o conjugado de partida de um rotor de
barras profundas (diferença de −35 % a −79 % nos três motores). O simulador mostra esse desvio
como aviso (regra 4), não o esconde. Uma gaiola dupla resolveria e fica como próximo passo.

## 4. ATmega328P (Arduino Uno e Nano)

Fonte: Microchip, documentação on-line "Automotive Silicon Errata and Data Sheet Clarification"
do ATmega328P, seção 3.6.1.2 (DC Characteristics): VIL ≤ 0,3 VCC, VIH ≥ 0,6 VCC, RPU 20 a 50 kΩ,
VOH ≥ 4,1 V e VOL ≤ 0,8 V a 20 mA e 5 V. É a versão automotiva (−40 a 125 °C); confira com o
datasheet comercial (Atmel-42735B, cap. 32), que não pôde ser lido até o fim.

## 5. Testes

- `tests/unit/machines/test_induction_fit.py`: ajuste do W22 16616834 (fonte e tolerâncias no
  docstring), aviso do conjugado de partida, divisão IEEE 112 e rastro do cálculo.
- `tests/unit/schematic/test_real_parts.py`: todo símbolo que era só didático tem peças reais;
  transformador com relação 234/36 V do datasheet; trifásico com P_sc/Sn; autotransformador;
  contator com 0,76/0,25 × Us; MOSFET e JFET canal P geram PMOS/PJF.
- `tests/analytic_vs_sim/test_as_drives.py::test_as_drv_09_catalogue_motor_weg_w22`
  (`AS-DRV-09`, ngspice): com o conjugado nominal, o SPICE dá o regime do circuito ajustado
  (rotação 0,2 %, corrente e conjugado 1 %) e o circuito dá 1175 rpm a 0,5 % e 4,41 A a 8 %.
- `tests/datasheet/test_ds_catalogue_values.py::test_web_values_in_excerpt`: cada valor novo
  aparece no trecho citado.

## Como usar

No Simulador, coloque o símbolo (por exemplo, Motor de indução trifásico) e escolha a peça do
catálogo no painel de propriedades. Os avisos da simulação dizem o que veio do datasheet e o que
continua didático.
