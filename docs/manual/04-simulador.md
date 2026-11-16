# 4. Simulador livre

Aba **Simulador**. O menu **Exemplos…** traz circuitos prontos para começar.

## Desenhar

- Escolha o símbolo na biblioteca (35 símbolos: passivos, fontes, chaves, dispositivos,
  transformador, fontes controladas, subcircuito) e clique na folha. A grade é de 20 px.
- Fios ligam terminais; um T sobre um fio conecta, um cruzamento não. Rótulos com o mesmo nome são
  o mesmo nó; `0` ou `gnd` é a referência.
- No painel de propriedades, escolha uma **peça real do catálogo** (diodos, Zener, TBJ, MOSFET,
  JFET, ampop, SCR, TRIAC, IGBT) ou deixe os parâmetros genéricos.
- Pontas: tensão, tensão diferencial, corrente e potência.

## Analisar

`.OP`, `.TRAN`, `.AC`, `.DC` (inclusive dupla), ruído; varredura paramétrica e de temperatura;
**Monte Carlo** e **pior caso** com as tolerâncias dos componentes e as faixas do datasheet (VZ,
hFE, VGS(th)).

Resultados: osciloscópio (dois eixos, cursores, zoom e medidas na janela), Bode, FFT/THD com
tabela de harmônicos, expressões (`v(out)*i(r1)`, `integ(p(q1))`, `movavg(...)`), gráfico XY e
estatística.

## Trocar arquivos

- **Importar netlist** / **Exportar netlist**: SPICE (`.model` e `.subckt` vão nas diretivas).
- **KiCad**: netlist `.net` dos componentes físicos (fontes e pontas ficam de fora).
- **CSV** dos vetores e **figuras** SVG/PNG/PDF com vírgula decimal.
- **Salvar**: `.circ.json` do esquemático.
