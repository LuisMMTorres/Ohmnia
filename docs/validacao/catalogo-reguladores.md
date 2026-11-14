# Catálogo: reguladores lineares (Fase 4)

Data: 2026-11-14. Status: valores transcritos como `extraido`, aguardando a sua conferência (D7).

Novos esquemas de categoria: `components/schemas/regulator.positive.yaml` e
`regulator.negative.yaml` (o negativo herda do positivo; tensões e correntes em módulo). Obrigatórios
para liberar: `Tj_max`, `Rth_ja`, `Rth_jc`. Os valores ficam nas unidades do datasheet (mV, mA, µA)
para o teste DS-*, que procura cada número na página citada do PDF.

| Arquivo | Peças | Datasheet | Revisão | SHA-256 (início) |
|---|---|---|---|---|
| `regulator/onsemi-mc7805c-mc7815c.yaml` | MC7805CT, MC7812CT, MC7815CT | onsemi MC7800/D, [PDF](https://www.onsemi.com/pdf/datasheet/mc7800-d.pdf) | Rev. 29, nov. 2021 | 0d716b89… |
| `regulator/onsemi-mc7905c-mc7915c.yaml` | MC7905CT, MC7912CT, MC7915CT | onsemi MC7900/D, [PDF](https://www.onsemi.com/pdf/datasheet/mc7900-d.pdf) | Rev. 21, out. 2021 | a2462056… |
| `regulator/onsemi-lm317.yaml` | LM317T | onsemi LM317/D, [PDF](https://www.onsemi.com/pdf/datasheet/lm317-d.pdf) | Rev. 18 | 19ef73a1… |
| `regulator/onsemi-lm337.yaml` | LM337T | onsemi LM337/D, [PDF](https://www.onsemi.com/pdf/datasheet/lm337-d.pdf) | Rev. 11, out. 2021 | 75dba59d… |

Parâmetros transcritos (quando o datasheet traz): VO e faixa, Vref, IAdj, VI máx., VI−VO máx. e mín.,
VI mínima de regulação, queda (dropout), IQ, IO máx., corrente de pico e de curto, carga mínima,
regulação de linha e de carga, rejeição de ondulação, RθJA, RθJC, TJ máx. e de armazenamento.

## Pontos para conferir com atenção

- **LM337, IO máx.:** as colunas da tabela foram transcritas como impressas (− / 1,5 / 2,2 A);
  confira o alinhamento com a linha da tabela.
- **LM337, RθJC:** a tabela de características dá 4,0 °C/W típico; a de máximos absolutos pode
  dar outro valor (está na nota do arquivo).
- **LM337, Vref:** em módulo; o datasheet dá −1,20 / −1,25 / −1,30 V.
- **VI−VO mín. dos ajustáveis:** é o menor diferencial da faixa em que Vref é especificada; o
  módulo usa como limite de queda (não é o dropout medido do fabricante).
- **78xx/79xx:** o projeto usa `VI_reg_min` transcrito (entrada mínima da linha de regulação), não
  uma queda derivada.

## Testes

- `DS-*` (`tests/datasheet/test_ds_catalogue_values.py`): cada valor com página aparece no texto do
  PDF baixado; passa para os quatro arquivos.
