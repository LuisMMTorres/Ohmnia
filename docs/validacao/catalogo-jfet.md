# Catálogo: JFET canal N (Fase 4, acréscimo)

Data: 2026-11-14. Status: valores transcritos como `extraido`, aguardando a sua conferência (D7).

Novo esquema de categoria `components/schemas/jfet.n.yaml`. Obrigatórios para liberar: `IDSS`,
`VGS(off)`, `Ptot`, `Tj_max`. Demais: VDS, VDG, VGSR, IG, derating de Ptot, Tstg, V(BR)GSS, IGSS,
yfs, yos, Ciss e Crss.

| Arquivo | Peças | Datasheet | Revisão | SHA-256 (início) |
|---|---|---|---|---|
| `jfet/onsemi-2n5457-2n5458.yaml` | 2N5457, 2N5458 | onsemi 2N5457/D, [PDF](https://www.onsemi.com/pdf/datasheet/2n5457-d.pdf) | Rev. 6, fev. 2010 | d547280c… |
| `jfet/onsemi-mpf102.yaml` | MPF102 | onsemi MPF102/D, [PDF](https://www.onsemi.com/pdf/datasheet/mpf102-d.pdf) | Rev. 3, jan. 2006 | c6022bcb… |

## Pontos para conferir com atenção

- **Fonte Symbol:** o texto do PDF mostra "mmhos" para µmhos (yfs, yos) e "mA" para µA em alguns
  campos; os valores estão em µS com nota no arquivo. Confira a unidade no PDF.
- **IDSS e VGS(off):** a dispersão é grande (2N5457: IDSS 1 a 5 mA, VGS(off) −0,5 a −6 V). O
  modelo usa IDSS típico e VP = 2·IDSS/|yfs| típico (Shockley), e avisa quando VP cai fora da faixa
  de VGS(off) do datasheet.
- **Ciss e Crss:** usados como capacitâncias constantes (CGS = Ciss − Crss, CGD = Crss) no fH do
  amplificador fonte comum.

## Uso nos projetos

DM-BIAS (`jfet_auto`, `jfet_divisor`) e DM-SSA (`FCJ`). A dissipação é conferida com Ptot referido
a 25 °C pelo derating do datasheet (os JFETs de sinal não trazem RθJA). Derating didático:
VDS × 1,3 e Ptot × 1,5; industrial: × 1,5 e × 2,0.

## Testes

`DS-*` (`pytest -m datasheet`) procura cada valor na página citada do PDF: sem faltas na conferência
local de 2026-11-14.
