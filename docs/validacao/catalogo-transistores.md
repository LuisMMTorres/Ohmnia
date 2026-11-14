# Validação: transistores e bancadas BD-TBJ e BD-FET (Fase 2, 3ª entrega)

Data: 2026-11-14. Status: aguardando revisão do usuário.

## O que foi entregue

- Categorias novas: `bjt.npn`, `bjt.pnp` (tensões e correntes em módulo) e `mosfet.n`.
- 33 componentes, 1 140 valores, transcritos dos datasheets oficiais (tabelas conferidas na
  imagem da página).
- Bancada BD-TBJ: curvas de saída IC × VCE com IB constante (modelo de transporte de
  Ebers-Moll com efeito Early), β e ro no ponto de operação, VCE(sat) do datasheet sobre o
  gráfico, ajuste de BF ao hFE.
- Bancada BD-FET: curvas de saída ID × VDS (modelo quadrático, SPICE nível 1), corrente de
  saturação, ponto de RDS(on) do datasheet, ajuste de VT a VGS(th) e de KP a RDS(on).

## Componentes

| Arquivo | Categoria | Partes | Datasheet |
|---|---|---|---|
| `bjt/onsemi-bc546-bc548.yaml` | NPN | BC546B, BC547A/B/C, BC548B/C | onsemi BC546/D, Rev. 8 (marcado OBSOLETE) |
| `bjt/onsemi-bc556b-bc558b.yaml` | PNP | BC556B, BC557A/B/C, BC558B | onsemi BC556B/D, Rev. 3 |
| `bjt/onsemi-p2n2222a.yaml` | NPN | P2N2222A | onsemi P2N2222A/D, Rev. 7 |
| `bjt/onsemi-2n3904.yaml` | NPN | 2N3904 | onsemi 2N3904/D, Rev. 3 |
| `bjt/onsemi-2n3906.yaml` | PNP | 2N3906 | onsemi 2N3906/D, Rev. 4 |
| `bjt/onsemi-bd135-bd139.yaml` | NPN | BD135, BD137, BD139 | onsemi BD135/D, Rev. 18 |
| `bjt/onsemi-tip31-tip32.yaml` | NPN/PNP | TIP31G a TIP31CG, TIP32G a TIP32CG | onsemi TIP31A/D, Rev. 17 |
| `bjt/onsemi-tip120-tip127.yaml` | NPN/PNP Darlington | TIP120 a TIP122, TIP125 a TIP127 | onsemi TIP120/D, Rev. 10 |
| `mosfet/vishay-irf540.yaml` | MOSFET N | IRF540 | Vishay 91021, Rev. C |
| `mosfet/vishay-irfz44.yaml` | MOSFET N | IRFZ44 | Vishay 91291, Rev. C |

Pontos que pedem atenção na revisão:

- **BC546–BC548:** o datasheet está marcado como OBSOLETE (situação: obsoleto). As linhas de
  hFE a 10 µA e 100 mA do grupo C citam só o BC548C; o BC547C ficou sem esses dois pontos.
- **TIP31G:** DISCONTINUED (NRND). **BD135TG** também, mas o BD135G segue ativo.
- **IRFZ44:** Qrr impresso em **nC** (0,53/0,80), o que não combina com trr = 120 ns e
  IF = 51 A (o IRF540 da mesma série traz µC). Ficou **a verificar**.
- **IRF540/IRFZ44:** o datasheet é da Vishay (IRF540, não IRF540N da Infineon; o site da
  Infineon não respondeu ao download automático).
- Os IRF não dão VGS(th) típico; o ajuste da bancada usa o ponto médio da faixa e avisa.

Sugestão de amostra: BC548B, 2N3904, TIP31CG e IRF540.

## Verificação

1. DS: todos os 1 140 valores encontrados na página citada.
2. AS-TBJ-01: IC(VCE) do modelo × ngspice (IB = 10 e 30 µA): 0,1 %.
3. AS-FET-01: ID(VDS) do modelo × ngspice nível 1 (VGS = 4, 5 e 6 V): 0,1 %.
4. Suíte completa: 3 294 testes Python e 9 de interface passando, cobertura 96 %.

## Limitações

- O modelo do TBJ não tem queda de ganho em alta corrente (IKF) nem resistências; com BF
  ajustado ao hFE em baixa corrente, ele superestima IC perto da corrente máxima.
- O modelo quadrático do MOSFET é didático: um MOSFET de potência real desvia muito dele em
  alta corrente. O ponto de RDS(on) aparece no gráfico para mostrar essa diferença.
- Complementares BD136/138/140 e MOSFETs canal P ficam para um próximo lote.
