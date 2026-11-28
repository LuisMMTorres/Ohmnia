# Biblioteca do esquemático: 555, potenciômetros e trimpots — revisão

Pedido (28/11/2026): incluir o CI 555 na biblioteca de componentes do esquemático, criar um
menu de circuitos integrados, levar o potenciômetro para junto dos resistores, abrir a
biblioteca com os menus fechados, incluir trimpots com modelos reais, melhorar os símbolos de
potenciômetro e trimpot no esquemático e na protoboard e deixar legíveis os nomes dos pinos
dos CIs na protoboard.

## O que mudou

| Item | Onde |
| --- | --- |
| Menus da biblioteca começam fechados | `frontend/src/pages/SchematicPage.tsx` |
| Menu **Circuitos integrados**: ampop e Temporizador 555 | `schematic/library.py` (grupo do ampop), `schematic/ic_symbols.py` |
| Potenciômetro e **Trimpot** em Passivos, logo após o resistor | `schematic/cosim_symbols.py`, `frontend/src/schematic/palette.ts` |
| Símbolo do potenciômetro (seta no cursor) e do trimpot (barra de ajuste em T), terminais 1-2-3 | `frontend/src/schematic/symbols.tsx` |
| Lista de peças separada: trimpots só no Trimpot, potenciômetros de painel só no Potenciômetro | `api/schematic.py` (`symbol_takes`) |
| Encapsulamentos reais na protoboard (3386P, 3362P, 3296W, PTV09A, PDB181-K) | `breadboard/packages.py`, `PackageArt.tsx` (`PotBody`), `routing.py` |
| Genérico desenhado como peça de referência: potenciômetro = Bourns PTV09A-4020F-B103, trimpot = Bourns 3386P-1-103LF | `breadboard/pinout.py` |
| Nomes dos pinos: número junto da perna e nome escrito na perpendicular | `PackageArt.tsx` (`PinNameLabel`) |

## Modelo do 555 (símbolo `timer555`)

Construído pelo diagrama de blocos do TI NE555 (SLFS022K, rev. K): divisor interno VCC–CONT–
(1/3)–GND, comparador de limiar (THRES > CONT), comparador de disparo (TRIG < CONT/2), báscula
SR com prioridade RESET > TRIG > THRES (nota da tabela 6-1), estágio de saída e transistor de
descarga. Valores padrão = NE555P do catálogo, p. 5 (coluna típica):

| Parâmetro | Valor | Origem |
| --- | --- | --- |
| Limiar do RESET | 0,7 V | RESET voltage level |
| VCC − VOH | 1,7 V | VOH = 13,3 V com VCC = 15 V, 100 mA |
| Resistência de saída alta | 8 Ω | (13,3 − 12,5) V / (200 − 100) mA |
| VOL | 0,1 V | VCC = 15 V, 10 mA |
| Resistência de saída baixa | 7,5 Ω | (0,4 − 0,1) V / (50 − 10) mA |
| Descarga ligada | 18,75 Ω | 0,15 V com 8 mA |
| ICC | 10 mA a 15 V | proporcional a VCC no modelo |
| Resistores do divisor | 5 kΩ cada | **didático**: o datasheet TI não informa |

Com o NE555P escolhido no catálogo, esses valores saem do registro (`ic_value`).

Limitações: VOL acima de 50 mA cresce mais depressa na peça real (2 V a 100 mA) e o modelo é
linear; bordas de saída de ~1 ns (as de 100 ns do datasheet geravam oscilação numérica com
passos longos); corrente de entrada de RESET/TRIG/THRES desprezada (1 GΩ). RESET aberto fica
em nível baixo: ligue-o a VCC.

Teste (`tests/unit/cosim/test_timer555.py`): astável RA = 1 kΩ, RB = 10 kΩ, C = 100 nF,
VCC = 15 V. t_H = (RA + RB)·C·ln 2 (TI SLFS022K, 7.2.2); t_L = RB·C·ln((2/3·VCC − V_D)/(1/3·VCC
− V_D)), com V_D = VCC·r_dis/(RA + r_dis) a tensão que sobra no DISCH. Tolerância 1 %. O
capacitor oscila entre 5 V e 10 V (1/3 e 2/3 de VCC).

## Peças reais (status `extraido`, falta a sua revisão)

| Peça | Encapsulamento | Datasheet (SHA-256) |
| --- | --- | --- |
| Bourns 3362P-1-103LF (**nova**) | trimpot 1/4", volta única | [3362.pdf](https://www.bourns.com/docs/Product-Datasheets/3362.pdf) `6f357bcb…0de3` |
| Bourns 3386P-1-103LF (pinagem nova) | trimpot 3/8", volta única | [3386.pdf](https://www.bourns.com/docs/Product-Datasheets/3386.pdf) `2b4a3fb7…6bb` |
| Bourns 3296W-1-103LF (pinagem nova) | trimpot multivoltas | [3296.pdf](https://www.bourns.com/docs/Product-Datasheets/3296.pdf) `8492a5d6…aef` |
| Bourns PTV09A-4020F-B103/B104 (pinagem nova) | potenciômetro 9 mm | [ptv09.pdf](https://www.bourns.com/docs/Product-Datasheets/ptv09.pdf) `411cdb6a…f28558` |
| Bourns PDB181-K420K-103B/254B/503B (pinagem nova) | potenciômetro 17 mm | [pdb18.pdf](https://www.bourns.com/docs/Product-Datasheets/pdb18.pdf) `19697d1d…972d` |
| TI NE555P (papéis dos pinos) | DIP-8 | SLFS022K `a3756e59…f4a6` |

Pinagem dos potenciômetros e trimpots: 1 = CCW (anti-horário), 2 = WIPER (cursor), 3 = CW
(horário); no simulador, posição 0 do cursor = pino 1. Os terminais de 5,0 mm do PTV09A e do
PDB181-K são dobrados para dois furos (5,08 mm). Os pinos em triângulo do 3386P e do 3362P
ocupam três fileiras seguidas da protoboard.

O que conferir: R, tolerância, potência, tensão máxima, ângulo e vida do 3362P (p. 1 e 2);
pinagens e páginas de todos; se o 3386P de referência é o modelo que você usa em aula.

Alpha (potenciômetros de 16 mm): os sites do fabricante não respondem na rede do ambiente;
fica para quando houver o PDF (o PDB181 de 17 mm ocupa esse papel por enquanto).

## Capturas

`/mnt/project-files/capturas/biblioteca-555-potenciometros/`: biblioteca fechada e aberta,
símbolos no esquemático, montagem automática na protoboard, NE555P com os nomes dos pinos e
trimpot 3386P selecionado.
