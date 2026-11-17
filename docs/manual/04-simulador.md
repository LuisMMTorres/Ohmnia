# 4. Simulador livre

Aba **Simulador**. O menu **Exemplos…** traz circuitos prontos para começar.

## Área de trabalho assistida

O simulador é a tela inicial do aplicativo. Na vista **Esquemático**, ele organiza o trabalho
em três etapas:

1. **Circuito:** desenhe o esquemático ou abra um exemplo. Use **Adicionar componente** para
   expandir a biblioteca; **Recolher biblioteca** libera mais espaço para o desenho. As ferramentas
   de fio, seleção e pontas de prova continuam visíveis com a biblioteca recolhida.
2. **Configurar análise:** escolha as análises, varreduras e condições. O botão abre
   o painel ao lado do esquemático, sem apagar as entradas do circuito.
3. **Resultados:** fica disponível após enviar uma simulação. O botão **Simular** abre esse
   painel ao lado do esquemático, onde aparecem o andamento, os resultados ou as mensagens de erro.

O painel **Propriedades** acompanha a seleção do desenho. Também é possível escolher uma peça
pela lista **Componente selecionado**, sem precisar acertar o símbolo com o mouse.
Os botões alternam o painel visível, sem rolar a página e sem perder os valores configurados.
Em telas estreitas, o painel escolhido ocupa a largura disponível; volte a **Circuito** para editar.

A navegação superior dá acesso às demais áreas. Os links com `#simulator`, `#design`, `#catalog`,
`#bench` e `#imports` continuam disponíveis; os botões Voltar e Avançar do navegador acompanham
a área selecionada.

### Nomes dos nós e sinais dos resultados

Ative **Exibir nomes dos nós** para mostrar os nomes automáticos (como `n001`) e o terra
no desenho. Os nomes vêm da netlist do circuito atual; alterações atualizam o mapeamento.
Rótulos inseridos manualmente continuam visíveis, pois também definem conexões elétricas.
Se o circuito estiver incompleto e não gerar uma netlist, a interface informa o motivo.

Os resultados oferecem somente as **pontas de prova adicionadas ao circuito** e expressões
adicionadas explicitamente pelo usuário. Cada análise mostra as probes disponíveis nela.
Sem probes, adicione-as e simule novamente. A lista usa as probes da simulação executada,
mesmo que o desenho seja editado depois. O ngspice continua calculando os nós necessários
para resolver o circuito; o filtro controla a visualização, não as equações da simulação.
Na análise de ruído, também aparecem os sinais de ruído da saída e da referência configuradas
na própria análise (`onoise` e `inoise`).

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
