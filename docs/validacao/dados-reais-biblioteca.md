# Dados reais na biblioteca do simulador (2026-11-21)

Pedido: conferir se as peças da biblioteca têm dados reais (de datasheet). As genéricas
continuam disponíveis, mas cada símbolo deve aceitar também peças reais.

Todos os 494 registros do catálogo têm fonte de fabricante (documento, revisão e página). Todos
estão como **rascunho**: entram no simulador com aviso de "não revisado" e, pela regra 5, nunca
entram em seleção automática.

## Símbolos ligados ao catálogo nesta entrega

| Símbolo | Categoria do catálogo | O que vem do datasheet |
|---|---|---|
| Resistor | `resistor.fixed` (14 séries) | P nominal e tensão máxima (quando a série tem um só valor); aviso se o valor está fora da faixa da série |
| Capacitor | `capacitor.fixed` (10) | Tensão nominal (quando única); aviso de faixa de capacitância |
| Indutor | `inductor.fixed` (6) | Aviso de faixa; I_rms e I_sat só quando o registro tem um único valor |
| MOSFET canal P | `mosfet.p` (BS250, IRF9540N) | Modelo PMOS de nível 1 (VGS(th) e RDS(on)) e limites VDS, VGS, ID, IDM, Ptot |
| JFET canal P | `jfet.p` (2N5460) | Modelo PJF (IDSS e yfs) e limites VDG e Ptot |
| Transformador monofásico / de 4 bobinas | `magnetic.transformer` (Triad VPT24-1040) | Vp, Vs e S de placa (o VPT24-1040 é 115 + 115 V / 12 + 12 V, 25 VA) |
| Inversor de frequência | `drive.vfd` (WEG CFW100 … CFW900, MW500) | Frequência de chaveamento |
| Soft-starter | `drive.soft_starter` (WEG SSW, ABB PSTX) | Identificação da peça (os registros são de família) |
| Driver de passo | `drive.stepper` (Oriental AR) | Identificação da peça |

Os registros de resistores, capacitores, indutores e acionamentos descrevem **séries ou
famílias**. Um limite dado como faixa (por exemplo, "50 a 500 V" numa série de capacitores)
pertence a modelos diferentes da série e por isso não é verificado. O valor (R, C, L) continua o
do esquemático.

Correção: o JFET canal P genérico tinha VTO = +2 V, o que no ngspice o deixa cortado com VGS = 0.
Agora é −2 V, a convenção do SPICE para depleção, conferida numa simulação.

## Já tinham peças reais

Diodos, Zener, NPN, PNP, MOSFET N, JFET N, IGBT, SCR, TRIAC, ampop, LED, lâmpada, motor CC, motor
de passo, relé, chaves e botões, sensores (LM35, Pt100, DS18B20, KTY81, DHT22, BME280, ACS712,
Hall, pressão, ultrassônico, LDR, NTC, potenciômetro), Arduino, ESP32, Raspberry Pi Pico e CLP.

## Ainda só didáticos (sem peça real no catálogo)

- Motor de indução (3 e 12 terminais): precisa do catálogo do fabricante (WEG W22, por exemplo).
  Os dados de placa (potência, corrente, rendimento, cos φ, Ip/In, Cp/Cn, Cmax/Cn, J) permitem
  estimar o circuito equivalente.
- Contator e aquecedor: precisam de datasheet (por exemplo, WEG CWM).
- Autotransformador e transformadores trifásicos: não há registro no catálogo.
- Transmissores 4-20 mA: o catálogo tem XTR105/115/116/117, Phoenix e Novus, mas o símbolo é um
  modelo de laço genérico; a ligação fica para depois.
- Fontes e elementos ideais (fontes de tensão e corrente, fontes controladas, terra, subcircuito)
  e o termopar (funções da NIST ITS-90) não precisam de peça.

## Testes

- `tests/unit/schematic/test_parts.py`: IRF9540N e 2N5460 conduzem com polarização negativa;
  PJF genérico conduz 4 mA com VGS = 0.
- `tests/unit/schematic/test_stress.py`: limites dos passivos do catálogo e aviso de faixa.
- `tests/unit/schematic/test_transformers.py`: VPT24-1040 em série dá 24 V.
- `tests/unit/cosim/test_drives.py`: CFW500 leva 5 kHz ao SPWM.
