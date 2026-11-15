# Validação: importação de datasheets em PDF (Fase 8)

Data: 2026-11-15. Status: aguardando a sua aprovação.

A nova aba **Importar datasheet** recebe o PDF do fabricante e propõe os valores dos parâmetros. Cada
valor vem com a página, o trecho literal e a posição na página. Nada entra no catálogo sem duas
confirmações suas: aceitar o valor na importação e conferi-lo na revisão. O componente importado
nasce **em revisão**, com os valores **extraídos**. Só entra na seleção automática depois que todos
os obrigatórios forem conferidos (regra 5, sem exceção).

## O que foi feito

| Item da especificação (4.7) | Onde | Situação |
|---|---|---|
| Upload do PDF com hash | `POST /api/v1/datasheets`; `datasheets/store.py` (SHA-256, fora do repositório) | ✅ |
| Extração de texto e tabelas | `datasheets/extract.py`: palavras com posição, reagrupadas em linhas visuais | ✅ |
| OCR para PDF digitalizado | Tesseract embutido no PyMuPDF, ativado automaticamente em página sem texto | ✅ (precisa dos arquivos `tessdata`) |
| Identificação da categoria | `mapping.rank_categories`: símbolos encontrados + palavras-chave da 1ª página | ✅ sugestão; você confirma |
| Mapeamento para o esquema, com página e trecho | `datasheets/mapping.py` (regras) e `aliases.yaml` | ✅ |
| Apoio de LLM com saída estruturada | `datasheets/llm.py` (Claude Opus 5.5, JSON validado por esquema) | ✅ opcional (D9) |
| Digitalização de curvas, eixos lin/log | `datasheets/digitize.py`; aba **Curvas** da revisão | ✅ três modos |
| Importação de modelos SPICE do fabricante | `datasheets/spice_import.py`; aba **Modelos SPICE** | ✅ com verificação no ngspice |
| Ajuste de modelo SPICE com relatório de erro | `datasheets/fit.py` | ✅ diodo, TBJ, MOSFET |
| Tela de revisão lado a lado (PDF × campos) | importação e revisão destacam no PDF a linha de origem | ✅ |

### Como o mapeamento por regras decide

1. **Linha visual.** As tabelas de datasheet raramente têm bordas. O texto é reagrupado em linhas
   pela posição vertical das palavras, de uma margem à outra da página.
2. **Símbolo.** Cada símbolo do esquema é procurado com e sem espaços ("V RRM" = "VRRM"), além das
   grafias de `aliases.yaml` (θJA, RthJA, IO para IF(AV)…). Um símbolo seguido de "=" é condição de
   ensaio, não parâmetro. Sem símbolo na linha, vale a descrição ("peak repetitive reverse
   voltage"), com confiança menor.
3. **Posição mín./típ./máx.** Vem do cabeçalho "Min Typ Max" da tabela, quando existe. Em tabela de
   família (várias colunas de part number), vem da coluna do seu part number. Sem nenhum dos dois,
   um limite absoluto é máximo e uma característica com valor único também vai para máximo, **com
   nota pedindo conferência**. Faixas como "−55 to +150 °C" alimentam Tj_min e Tj_max.
4. **Condições.** Pares "NOME = valor unidade" da linha (IF = 2,0 A, TA = 25 °C, tp = 8,3 ms) viram
   condições com unidade. O texto original também fica guardado na nota do parâmetro.
5. **Filtro de unidade.** Se a unidade lida não tem a dimensão que o esquema espera, a linha é
   descartada. É a principal defesa contra falsos positivos.

Cada candidato mostra a origem (regras, modelo de linguagem ou manual), uma confiança e as notas de
toda inferência feita. A página lida por OCR ganha a nota "confira dígitos e unidade".

### Modelo de linguagem (D9): opcional e verificado

A caixa só fica disponível com o pacote `anthropic` instalado (`uv sync --extra llm`) e uma
credencial da API da Anthropic. O PDF é enviado à API apenas quando você marca a caixa naquela
importação. O modelo precisa citar, para cada valor, a página e o trecho literal. O sistema então
confere:

- se o trecho existe no texto daquela página (extraído localmente);
- se cada número informado aparece no trecho;
- se a unidade é compatível com o esquema.

O que falhar aparece na lista **propostas descartadas**, com o motivo, e não vira candidato. Isso
impede que um valor "plausível" entre sem estar no PDF (regra 1). A D9 continua sua: sem chave, o
fluxo por regras e manual é completo.

### Digitalização de curvas

Primeiro você calibra os eixos: duas marcas por eixo, linear ou logarítmico. Depois marca a área do
gráfico. A curva pode ser obtida de três formas:

- **Traços vetoriais.** A maior parte dos datasheets desenha os gráficos como vetores. O sistema
  lista os traços dentro da área, com a cor de cada um, e você escolhe. Os pontos são os vértices
  do próprio PDF, exatos.
- **Seguir cor.** Para página digitalizada: você clica sobre a curva e o sistema segue aquela cor
  coluna a coluna.
- **Cliques.** A precisão é de um pixel de tela, cerca de 1 ponto do PDF no zoom normal da tela.

A curva guarda grandezas, unidades, escalas, condições (ex.: Tj = 25 °C), página, área, método e
quem digitalizou.

### Ajuste de modelo SPICE

| Dispositivo | Parâmetros | Dados usados |
|---|---|---|
| Diodo (`D`) | IS, N, RS (+ TNOM) | curva IF×VF (mínimos quadrados no erro relativo de VF) |
| | BV, IBV | V(BR) ou VRRM e IR; no Zener, VZ e IZT |
| | CJO (VJ = 1 V, M = 0,5) | Cj a VR do datasheet, levada a 0 V |
| | TT | trr, TT ≈ trr / ln(1 + IF/IR) |
| TBJ (Gummel-Poon reduzido) | IS, NF | curva VBE×IC, ou VBE(on) a IC com NF = 1 |
| | BF, IKF | curva hFE×IC do pico em diante, hFE = BF/(1 + IC/IKF) |
| MOSFET nível 1 | VTO, KP | √ID × VGS da curva de transferência, ou VGS(th) e gfs |
| | RD | RDS(on) menos a resistência do canal do modelo |

Depois do ajuste, o `.model` final é **simulado no ngspice** em cada ponto da curva. O erro
reportado (RMS e máximo) é o simulado (regra 4 aplicada ao modelo). O relatório lista a origem de
cada parâmetro e todas as premissas. Com poucos pontos para os parâmetros ajustados, o relatório
avisa que o erro não mede a qualidade do modelo. As equações citam o manual do ngspice e Antognetti
& Massobrio (2ª ed., caps. 1–3); capítulo e número de equação ainda precisam ser conferidos no livro
impresso, como nas fases anteriores.

## Resultados dos testes

| Teste | O que verifica | Resultado |
|---|---|---|
| `tests/unit/datasheets/test_extract_mapping.py` | unidades e números de datasheet; linhas; OCR; Mín./Típ./Máx.; faixas; condições; tabela de família; título com part number; ranking de categoria | ✅ 34 |
| `tests/unit/datasheets/test_llm.py` | trecho inventado, número fora do trecho, página e unidade erradas são rejeitados; cliente da API simulado (sem rede) | ✅ 5 |
| `tests/unit/datasheets/test_digitize.py` | calibração lin/log (propriedade, Hypothesis); traço vetorial recupera I = 1 nA·exp(V/50 mV) com erro < 0,1 %; seguir cor com mediana < 2 % | ✅ 4 |
| `tests/unit/datasheets/test_spice_import.py` | `.model` com continuação e comentários, `.subckt` com pinos; carga no ngspice; modelo ausente reportado | ✅ 4 |
| `tests/analytic_vs_sim/test_as_fit.py` (AS-FIT) | ajuste recupera parâmetros de modelos conhecidos gerados pelo ngspice: diodo (N ±2 %, RS ±5 %, erro VF < 1 %), TBJ (BF ±5 %, IKF ±15 %, erro hFE < 3 %), MOSFET (VTO ±1 %, KP ±2 %, erro ID < 1 %); aviso de ajuste subdeterminado | ✅ 4 |
| `tests/unit/api/test_imports_api.py` | upload → importação → edição → importar → revisão → liberação; curva, ajuste, modelo do fabricante, remoção | ✅ 6 |
| `tests/datasheet/test_ds_extraction.py` (DS-EXT) | regras × catálogo transcrito à mão, nos PDFs reais (rede) | ⏳ não executado (ver pendências) |
| Front-end (`vitest`) | calibração e leitura das condições da curva | ✅ 2 novos (34 no total) |
| Verificação no navegador | importação do PDF de teste, destaque no PDF, importação, aba Curvas (calibração, área, cliques, salvar), aba Modelos (importar e ajustar) | ✅ feito manualmente nesta máquina |

A suíte completa do backend está descrita em "Ambiente Windows", abaixo.

Os PDFs dos testes são **sintéticos e fictícios** (TESTE-D1…), gerados pelo próprio teste. Nenhum
valor de componente real foi escrito de memória (regra 1).

## Ambiente Windows (esta máquina)

O projeto passou a rodar no Windows 11. Instalação feita: Git, Python 3.12, uv, Node 26, Tesseract
(eng, por) e ngspice 47 em `%LOCALAPPDATA%\Programs\Spice64` (executável) e `Spice64_dll` (DLL). As
variáveis `CIRCUITOS_NGSPICE_EXE` e `CIRCUITOS_NGSPICE_LIB` ficaram gravadas no usuário. Correções
necessárias, todas com teste:

- **DLL do ngspice.** O Python não procura dependências na pasta da DLL. O backend agora registra
  essa pasta (`os.add_dll_directory`). O pacote de DLL da versão 47 não traz `sndfile.dll` e
  `samplerate.dll`; foram copiadas da pasta do executável, da mesma versão.
- **Memória.** O ngspice 47 estima a memória da saída antes de simular e aborta se não couber.
  Antes isso virava um `ValueError` sem explicação; agora é a mensagem "Memória insuficiente para
  guardar os resultados", com sugestões. Os três testes de tempo limite passaram a usar saída leve.

## Limitações conhecidas

- O mapeamento por regras depende de o PDF ter a tabela em linhas. Tabelas com valores quebrados em
  duas linhas (condições numa linha, valor na outra) perdem as condições; o valor ainda é achado.
- A categoria sugerida pode errar entre famílias próximas (retificador × rápido × Schottky). Sempre
  confira o campo antes de importar.
- Ajuste de modelo só para diodo, TBJ e MOSFET. IGBT, tiristores e amp-ops ficam com o modelo do
  fabricante ou o comportamental das fases anteriores.
- O TBJ não modela a queda do hFE em correntes baixas (ISE, NE) nem o efeito Early, sem dados. O
  MOSFET é nível 1 (lei quadrática), sem as capacitâncias; isso é suficiente para o ponto de
  operação e a curva de transferência, mas não para comutação.
- Cliques manuais têm a resolução de um pixel de tela; para precisão, use o traço vetorial.

## Pendências para você

1. **D9.** Decidir se haverá chave da API da Anthropic (IFMA ou pessoal). Sem ela, tudo funciona
   pelas regras e pela digitação manual.
2. **DS-EXT.** O teste que compara a importação automática com o catálogo transcrito baixa os PDFs
   dos fabricantes (`pytest -m datasheet`). Ele foi interrompido quando o iniciei e não rodou. Diga
   se posso executá-lo: ele mede quantos valores a importação acerta, erra e deixa de achar nos
   datasheets reais.
3. **AS da Fase 5 no Windows.** Os casos `opnl_limitador` e `opnl_limitador_g2` falharam na primeira
   execução da suíte nesta máquina. Eles passavam no Linux, então é algo do ambiente, não desta
   fase. A investigação foi interrompida; fica registrada aqui.
4. Os cinco PDFs da onsemi com bytes novos (pendência da Fase 6) continuam aguardando seu OK.

## Próximo passo

Fase 9: relatórios completos, exportações (KiCad, se viável), instalador local, manual do usuário e
guia para novas topologias e componentes.
