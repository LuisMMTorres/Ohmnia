# Validação: catálogo de tiristores (Fase 2, 4ª entrega)

Data: 2026-11-14. Status: aguardando revisão do usuário (conferência dos dados quando for conveniente).

## Componentes transcritos (14 partes)

| Arquivo | Categoria | Partes | Datasheet |
|---|---|---|---|
| `onsemi-2n5060.yaml` | SCR de porta sensível, TO-92 | 2N5060, 2N5061, 2N5062, 2N5064 | onsemi 2N5060/D, Rev. 11, out. 2024 |
| `onsemi-mcr265.yaml` | SCR 55 A, TO-220AB | MCR265-4, -6, -8, -10 | onsemi MCR265/D, Rev. 3, ago. 2006 |
| `onsemi-mac97.yaml` | TRIAC de porta sensível, TO-92 | MAC97A4, A6, A8 | onsemi MAC97/D, Rev. 10, ago. 2013 |
| `onsemi-mac218a.yaml` | TRIAC 8 A, TO-220 isolado | MAC218A6FP, A8FP, A10FP | onsemi MAC218A6FP/D, Rev. 3, ago. 2006 |

Novos esquemas de categoria: `thyristor.scr`, `thyristor.triac` (herda do SCR e acrescenta
dv/dt de comutação) e `thyristor.diac`. Obrigatórios para liberar: VDRM, IT(RMS), ITSM, IGT, IH,
VTM e Tj máx. No TRIAC, IGT e VGT ficam por quadrante (`IGT@Q1` a `IGT@Q4`):
Q1 = MT2(+), G(+); Q2 = MT2(+), G(−); Q3 = MT2(−), G(−); Q4 = MT2(−), G(+).

## Como foi verificado

1. Tabelas lidas do texto do PDF. As unidades em µ (µA, µs, V/µs), que somem na extração de texto
   desses PDFs, foram conferidas nas páginas renderizadas.
2. **Teste DS (`pytest -m datasheet`):** os 442 valores foram encontrados na página citada. O
   teste passou a aceitar números sem zero à esquerda (".66"), comuns nas tabelas antigas.
3. Rastreabilidade: todo valor tem documento, revisão e página.

## Pontos para sua atenção na conferência

- **MAC97:** o quadro da primeira página anuncia 0,8 A RMS; a tabela de valores máximos dá
  IT(RMS) = 0,6 A a TC = 50 °C. Registrei 0,6 A, com nota.
- **MCR265:** a linha de IGT a −40 °C foi lida pela ordem dos números (típ. 40 mA, máx. 90 mA).
  Conferir na página 3.
- **ITSM dos TRIAC:** o datasheet especifica "um ciclo completo de 60 Hz"; registrei
  t_pulse = 16,7 ms. Nos SCR é meio ciclo (8,3 ms).
- **IL (corrente de travamento):** nenhum dos quatro datasheets informa. A bancada usa um valor
  didático ajustável e avisa.
- **2N5060:** IDRM e IH incluem RGK = 1 kΩ (nota 3 do datasheet).

## O que ficou de fora

- **DIAC:** o esquema existe, mas nenhum datasheet de fabricante pôde ser baixado deste ambiente
  (ST recusa a conexão; Littelfuse e Bourns respondem 403). O DB3, que é o DIAC usado em sala, entra
  quando houver acesso ao PDF oficial (você pode enviar o PDF da ST pelo projeto).
- **TIC106, BT136, BT151:** os sites da Bourns e da WeEn também bloquearam o download.
