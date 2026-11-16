# Validação: catálogo de dispositivos reais (Fase 12, decisão D13)

Data: 2026-11-16. Status: aprovada em 2026-11-16 (os registros novos seguem como rascunho até a revisão de cada um).

Pedido: buscar os datasheets que faltavam e cadastrar os dispositivos com as especificações reais,
usando manuais quando não houver datasheet, para simular e projetar com peças reais.

## Números

| | Antes | Depois |
|---|---|---|
| Itens da fila com PDF utilizável | 232 de 510 | 457 de 510 |
| Itens da fila cadastrados no catálogo | cerca de 70 | 440 |
| Registros no catálogo | 365 | 758 (393 novos) |
| Categorias com esquema | 24 | 77 |
| Parâmetros nos registros novos | | 3.868, cada um com página e trecho |
| Atributos em texto nos registros novos | | 950 (saída, protocolo, grau IP, material...) |

Registros novos por categoria: proximidade 19, transmissor 18, temperatura 16, D/A 14, resistor
fixo 14, medidor de energia 12, sensor de corrente 12, CI digital 11, potenciômetro 11,
fotoelétrico 11, capacitor 10, A/D 10, optoacoplador 10, nível 10, inversor 9, fusível 9, CLP 9,
SCR 9, TRIAC 9, interface 8, MOSFET N 8, motor de passo 8, Hall 8, pressão 8, chave 8,
soft-starter 7, indutor 6, sensor de tensão 6, placa 5, microcontrolador 5, JFET N 5, LED 5,
SSR 5, relé 5, e de 1 a 4 nas outras 34 categorias.

## Como foi feito

1. **Busca:** três rodadas de agentes. A primeira achou 146 dos 278 itens sem PDF. A segunda,
   aceitando manuais e catálogos, chegou a 226. A terceira buscou cópias em distribuidores para 40
   itens com link oficial que não responde a download automático (ST, Analog Devices, Microchip,
   Rockwell, loja dos motores de passo). Cada PDF foi conferido: assinatura %PDF, abertura,
   número da peça no texto e SHA-256. Os PDFs ficam em `D:\Downloads_net\Claude\datasheets-baixados`,
   e a fila (`data/datasheet-queue.yaml`) registra link, caminho, hash e de onde veio cada um.
2. **Esquemas:** 53 categorias novas (D13) e atributos em texto no registro.
3. **Transcrição:** 35 lotes de agentes. Cada um lê o texto do PDF página a página (ou a imagem
   da página quando o texto é ilegível), escolhe a categoria, escreve o registro com página,
   local e trecho, e passa no validador.
4. **Validador** (`validate_record.py`, na pasta de trabalho): carrega o registro como o catálogo
   carrega (modelo e esquema) e procura cada número na página citada do PDF.
   - Resultado: 393 arquivos, **0 erros**, 212 avisos.
   - Avisos: quase todos em PDFs digitalizados, lidos pela imagem (IRF9540N, IRLZ44N, CD4017,
     CD4511, 6 motores de passo, STM32F446 com PDF truncado). Os outros são formatos que o
     validador não reconhece: "4M7Ω", "10^7", unidade convertida de gauss para mT.

## Regras mantidas

- **Nenhum valor inventado.** O que o documento não diz ficou de fora. Valores sem símbolo no
  esquema estão nas notas, com página.
- **Todo registro novo é rascunho** (Claude, transcrição assistida). Nada entra na seleção
  automática antes da sua revisão (regra 5). Os testes de projeto usam só o conjunto já revisado,
  listado em `backend/tests/fixtures/catalogo-revisado.txt`; acrescente um arquivo ali quando
  liberá-lo.
- **Faixas de série:** num documento de série, o registro guarda a faixa entre os modelos, e as
  notas dizem isso.
- **Fabricante divergente:** quando o PDF é de outro fabricante (segunda fonte, ou a fila estava
  errada), o registro usa o fabricante do documento e anota.

## Peças reais na simulação

Os símbolos da co-simulação aceitam a peça do catálogo e tomam dela os valores:

| Símbolo | Categoria | Valores do registro |
|---|---|---|
| LM35 | sensor.temperature | sensibilidade |
| Pt100 | sensor.temperature | R0 |
| ACS712 | sensor.current | sensibilidade, resistência do primário, banda |
| Potenciômetro | resistor.variable | resistência |
| Relé | relay.electromechanical | tensão e resistência da bobina |
| Arduino, ESP32, CLP | board.mcu, plc | identificação (os valores elétricos seguem os da placa) |

O teste `tests/unit/cosim/test_catalogue_parts.py` confere isso com o Bourns 3296W de 10 kΩ.

## O que pedir a você

1. **Revisar e liberar** os registros que for usar. As dúvidas de cada transcrição estão nas notas
   do registro. As que mais merecem atenção:
   - **Tabela lida da imagem:** PC817, TIL111, MFR-25/50, LGU 470 µF, Nichicon UHE, CS5463,
     MAX485, LTC4151.
   - **Peça diferente da fila:**
     - BCG08-A1KM03PP (PDF do K1KM03PP), XMLP016BC21V (PDF do 21F), MM12-60APS-ZC0 (PDF do
       ZCK), YF-S201 (PDF do YF-21);
     - S55720-S102 (série QAA20), LT 308-S7 SP1 (sem o SP1).
   - **Catálogo geral ou manual de série:** WEG CLIC-02, PLC300, PLC500, LOGO! 8, S7-1200, Micro800,
     Modicon M221 (só guia de programação), soft-starters SSW.
   - **Valor calculado ou interpretado pelo agente:** 2N2646 (η sem símbolo na tabela), MAX6675
     (exatidão de 8 LSB × 0,25 °C), C106D (VDM = 0,67 × VDRM), ITSM do TIC106 (10 ms de 50 Hz).
2. **Os 53 itens sem PDF** (lista em `D:\Downloads_net\Claude\componentes-sem-datasheet.md`):
   - Endress+Hauser (26 documentos TI), ifm (6), Festo (6) e HBM (3) bloqueiam o download
     automático. Baixe pelo navegador e coloque na pasta de datasheets, ou autorize que eu baixe
     pelo seu Chrome.
3. **Os 17 itens com PDF sem dados:** J175 (o PDF só traz o J176), PBS-110 e HDSP-5103/HLMP-33xx/
   HLMP-3507 (PDF de outras peças), NTC 10D-11, catálogos gerais (Minco, Pyromation, HBM S01265),
   CM18-08BNP-KC1, Annubar 3051SFA, 3RW5, MV2 e SMC-50. Precisam de outro documento.

## Testes

- Validador: 393 registros, 0 erros.
- `test_catalogue_files_are_valid_and_traceable`: todo registro carrega e cita página. Agora um
  datasheet sem link é aceito só quando é a cópia local da fila, conferida pelo hash.
- Suíte completa do backend: 922 passam; falham só as 3 pendências antigas (`opnl_limitador` ×2 e `test_pt_inv_ma_linear`). Frontend: TypeScript, ESLint, Prettier e vitest sem erro.

## Limitações

- Não há tela de edição de atributos: eles aparecem na revisão do componente, só para leitura.
- A co-simulação usa só os valores mapeados acima. Os sensores industriais (proximidade, nível,
  pressão) ainda não têm símbolo de simulação próprio.
- Pinagens de protoboard não foram transcritas para os registros novos.
