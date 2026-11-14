# Catálogo: ampops, comparador e temporizador (Fase 5)

Data: 2026-11-14. Status: valores transcritos como `extraido`, aguardando a sua conferência (D7).

Esquemas de categoria novos em `backend/src/circuitos/components/schemas/`: `opamp`, `comparator` e
`timer`. Os projetos só usam uma peça depois de você revisar e liberar (regra 5).

| Arquivo | Peça | Datasheet | Revisão | SHA-256 (início) |
|---|---|---|---|---|
| `opamp/ti-lm741c.yaml` | LM741CP | TI LM741, SNOSC25D, [PDF](https://www.ti.com/lit/ds/symlink/lm741.pdf) | Rev. D, out. 2015 | 6f3bf3cb… |
| `opamp/ti-lm358.yaml` | LM358P | TI LM358, SNOSC16AB, [PDF](https://www.ti.com/lit/ds/symlink/lm358.pdf) | Rev. AB | 8277dff7… |
| `opamp/ti-tl071c.yaml` | TL071CP | TI TL07xx, SLOS080W, [PDF](https://www.ti.com/lit/ds/symlink/tl071.pdf) | Rev. W, jul. 2025 | d6e672f7… |
| `comparator/ti-lm311.yaml` | LM311P | TI LM111/LM211/LM311, SLCS007K, [PDF](https://www.ti.com/lit/ds/symlink/lm311.pdf) | Rev. K | 1877bb45… |
| `timer/ti-ne555.yaml` | NE555P | TI xx555, SLFS022K, [PDF](https://www.ti.com/lit/ds/symlink/ne555.pdf) | Rev. K, mar. 2026 | a3756e59… |

## Valores principais (típico, com mín./máx. quando o datasheet traz)

| Parâmetro | LM741CP | LM358P | TL071CP |
|---|---|---|---|
| Alimentação máx. | ±18 V | 32 V totais (±16 V) | 42 V totais (`VS_total_max`) |
| VOS | 2 mV (máx. 6) | 3 mV (máx. 7) | 3 mV (máx. 10) |
| IB / IOS | 80 nA / 20 nA | 20 nA / 2 nA | 65 pA / 5 pA |
| Rin | 2 MΩ (mín. 0,3) | — | 1 TΩ |
| A0 (Avol) | 200 V/mV (mín. 20) | 100 V/mV (mín. 25) | 200 V/mV (mín. 25) |
| GBW | 1,17 MHz por 0,35/tr (tr = 0,3 µs) | 0,7 MHz | 5,25 MHz |
| SR | 0,5 V/µs | 0,3 V/µs | 20 V/µs (mín. 8) |
| Excursão | ±13 V (VOM, VS = ±15 V) | VOH = V+ − 2 V; VOL = V− + 5 mV | ±13,5 V |
| CMRR | 90 dB (mín. 70) | 80 dB (mín. 65) | 100 dB (mín. 70) |
| PSRR | 96 dB (mín. 77) | 100 dB (mín. 65) | 100 dB (mín. 70) |

LM311P: VOS 2 mV, IB 100 nA, A0 200 V/mV, VOL 0,75 V, tempo de resposta 115 ns, saída em coletor
aberto até 40 V. NE555P: limiares 10 V e 5 V com VCC = 15 V (2/3 e 1/3), VOH 13,3 V, VOL 0,1 V,
descarga 0,15 V, deriva 50 ppm/K (monoestável) e 150 ppm/K (astável).

## Pontos para conferir com atenção

- **GBW do LM741C:** o datasheet não dá GBW para o LM741C. O modelo usa BW = 0,35/tr com o tr
  típico de 0,3 µs (nota 2 da tabela do LM741A, p. 6), o que dá 1,17 MHz. Se preferir 1 MHz, é só
  mudar o critério; o valor fica anotado na memória de cálculo.
- **TL071C, alimentação:** o datasheet dá a tensão total (V+ − V−) e por isso a chave é
  `VS_total_max`; as demais tensões estão em módulo.
- **CMRR e PSRR em dB:** o catálogo guarda o número em dB como está no datasheet. O modelo converte
  para V/V com 10^(dB/20) (relação de tensão). O PSRR do modelo vale por trilho, com a variação
  simétrica.
- **LM358:** a tabela 5.7 vem com VS = 5 V e o ganho com VS = 15 V; a excursão é por queda até o
  trilho (VOH_drop, VOL_drop).
- **NE555:** os limiares de catálogo (10 V e 5 V) são escalados para a VCC do projeto. A memória
  avisa que isso supõe o divisor interno ideal.

## Uso nos projetos

DM-OPA, DM-FIL, DM-OPNL, DM-OSC e DM-INST (ampops); DM-OPNL com `device = comparador` (LM311);
DM-OSC 555 (NE555). A escolha automática filtra a alimentação (simétrica ou total) e ordena por
preferência do módulo: maior SR nos osciladores e comparadores, menor VOS na instrumentação.

## Testes

`DS-*` (`pytest -m datasheet`) procura cada valor na página citada do PDF: 131 verificações destas
cinco peças, sem faltas na conferência local de 2026-11-14.
