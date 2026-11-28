# Revisão — NE555 (Texas Instruments) na Biblioteca

Arquivo: `data/components/timer/ti-ne555.yaml` (peça NE555P, PDIP-8).
Datasheet: Texas Instruments, *NA555, NE555, SA555, SE555*, SLFS022K, revisão K (março de 2026),
<https://www.ti.com/lit/ds/symlink/ne555.pdf>, SHA-256
`a3756e59fd06d0ba736edf9ffe71d99d2aae33fb7e49fedc86165a241179f4a6` (mesmo arquivo de
`D:\Downloads_net\baixar_250_datasheets\...\NE555_TI.pdf`).

## O que mudou

O NE555 já estava na Biblioteca com 16 parâmetros. Agora tem 44, todos da coluna
"NA555, NE555, SA555" do datasheet, com página e linha da tabela. Todos estão como `extraido`:
falta a sua conferência antes de liberar.

| Grupo | Parâmetros novos | Página |
|---|---|---|
| Condições recomendadas | VCC 4,5 V a 16 V; corrente de saída ±200 mA; TA 0 °C a 70 °C | 4 |
| Térmico (PDIP) | RθJC(topo) 77,8 °C/W; RθJB 61,0 °C/W | 5 |
| Limiares com VCC = 5 V | THRES 2,4 / 3,3 / 4,2 V; TRIG 1,1 / 1,67 / 2,2 V | 5 |
| RESET | nível 0,3 / 0,7 / 1 V; corrente 0,1 / 0,4 mA (em VCC) e 0,4 / 1,5 mA (em 0 V, saindo do pino) | 5 |
| CONT em aberto | 9 / 10 / 11 V (VCC = 15 V); 2,6 / 3,3 / 4 V (VCC = 5 V) | 6 |
| VOL | 15 V: 50 mA, 100 mA, 200 mA (só típico); 5 V: 5 mA, 8 mA | 6 |
| VOH | 15 V, 200 mA (só típico 12,5 V); 5 V, 100 mA (mín. 2,75 V, típ. 3,3 V) | 6 |
| Corrente de alimentação | saída baixa 5 V; saída alta 15 V e 5 V | 6 |
| Comutação | sensibilidade à alimentação 0,1 / 0,5 %/V (monoestável), 0,3 %/V (astável); tr e tf 100 / 300 ns com CL = 15 pF | 7 |

Notas do registro: entradas não devem passar de VCC; ESD ±500 V HBM, ±1500 V CDM.

## Como conferir

1. Biblioteca → Temporizador → NE555P → abrir o datasheet ao lado e conferir cada linha.
2. Teste automático (baixa o PDF e procura cada número na página citada):
   `pytest -m datasheet tests/datasheet/test_ds_catalogue_values.py -k NE555` → 78 de 78 valores encontrados.

## Limitações

* Só a peça NE555P (PDIP). As cápsulas SOIC (D), SO (PS) e TSSOP (PW) têm outra resistência
  térmica e não foram cadastradas.
* As colunas SE555 e as linhas com TA = −55 °C a +125 °C ficaram de fora (são de outra peça).
* O teste `test_web_values_in_excerpt` já falhava antes desta mudança, nos contatores WEG CWM;
  não tem relação com o NE555.
