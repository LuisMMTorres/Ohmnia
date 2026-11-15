# Validação: catálogo de potência chaveada (Fase 6)

Data: 2026-11-15. Status: aguardando a sua conferência. Todos os valores estão com `status: extraido`;
nada entra na seleção automática antes da sua revisão (regra 5).

## Semicondutores e driver

| Arquivo | Categoria | Parte | Valores | Datasheet |
|---|---|---|---|---|
| `mosfet/vishay-irf840.yaml` | `mosfet.n` | IRF840 (500 V) | 43 | Vishay Siliconix 91070, S21-0883-Rev. E, 30-ago-2021 |
| `igbt/onsemi-fgh40n60smd.yaml` | `igbt.n` | FGH40N60SMD (600 V, 40 A, diodo antiparalelo) | 37 | onsemi FGH40N60SMD/D, Rev. 4 |
| `diode/onsemi-mbr20100ct.yaml` | `diode.schottky` | MBR20100CT (100 V, 2 × 10 A) | 15 | onsemi MBR20100CT/D, Rev. 1, jan-2015 |
| `diode/onsemi-mur1560.yaml` | `diode.fast` | MUR1560G (600 V, 15 A) | 14 | onsemi MUR1520/D, Rev. 11, out-2025 |
| `gate_driver/infineon-ir2110.yaml` | `gate_driver` | IR2110 (500 V, bootstrap) | 26 | Infineon (IR) PD60147 rev. V |

Esquemas novos: `igbt.n` (VCES, IC, VCE(sat), VGE(th), Qg, Eon, Eoff, Rth, …) e `gate_driver`
(VOFFSET, VCC, IO+, IO−, ton, toff, IQBS, IQCC, VBSUV, …).

Pontos para a sua conferência:

- **FGH40N60SMD:** o texto do PDF perde o símbolo µ (250 µA, µJ, A/µs); as unidades foram conferidas
  na figura da página. E_on e E_off a 400 V/40 A, 25 °C e 175 °C, R_g do ensaio no campo de condições.
- **IR2110:** IO+ e IO− (mín. 2 A e 2 A no datasheet) definem R_g mínimo em `DM-CMD`; IQBS máx. e
  VBSUV− entram no bootstrap.
- **MUR1560:** o documento cobre a família MUR1520–MUR1560; só a 1560 foi transcrita.

## Núcleos, materiais e carretéis

| Arquivos | Categoria | Itens | Valores por item | Fonte |
|---|---|---|---|---|
| `magnetic/ferroxcube-e*.yaml` | `magnetic.core` | E 16/8/5, 19/8/5, 20/10/6, 25/13/7, 30/15/7, 42/21/15, 42/21/20, 55/28/21, 65/32/27 | 15–16 | Ferroxcube, product specification de cada núcleo (2016) |
| `magnetic/ferroxcube-etd*.yaml` | `magnetic.core` | ETD 29, 34, 39, 44, 49, 54 | 15–16 | idem |
| `magnetic/ferroxcube-material-3c9*.yaml` | `magnetic.material` | 3C94, 3C96 | 9–10 | Ferroxcube, material specification (2008-09-01) |
| `magnetic/thornton-carretel-*.yaml` | `magnetic.bobbin` | EE 30/15/7, 42/21/15, 42/21/20 | 4 | Thornton, folha NEE (acessórios) |

Pontos para a sua conferência:

- Ae, le, Ve e AL sem entreferro, cotas do desenho (largura e altura da janela, perna central) e perda
  máxima por conjunto a 100 kHz/200 mT/100 °C, por núcleo.
- Pv do material: 3C96 tem três pontos típicos a 100 °C (o ajuste de Steinmetz fica exato); 3C94 tem
  dois pontos na mesma frequência, por isso α não é ajustado.
- Bsat mínimo a 100 °C limita B_max do projeto.

## Correção na liberação

Os TRIACs (`thyristor.triac`) têm IGT por quadrante (`IGT@Q1` … `IGT@Q4`), mas a regra de liberação
procurava `IGT`. Agora um obrigatório dado por condição é aceito quando todas as entradas com valor
estão revisadas. Sem essa correção, nenhum TRIAC podia ser liberado e `DM-CACA` ficava sem peça.

## Datasheets da onsemi baixados de novo

Em 2026-11-15 cinco PDFs da onsemi passaram a vir com outro hash: NCP1117, MC7900, MBR20100CT,
MUR420 (MUR460) e MUR1520 (MUR1560). Comparei o arquivo guardado com o novo: mesmo número de
páginas, mesma data de modificação e texto idêntico em todas as páginas; muda só a sequência de
bytes. O teste `DS-CATALOGO` recusa o arquivo novo (regra: revisar antes de trocar o hash), por isso
as 182 conferências desses cinco documentos falham num ambiente sem os arquivos antigos. Com os
arquivos guardados todas passam. Para resolver: trocar o `sha256` dos cinco registros pelo do
arquivo novo, com o seu OK.
