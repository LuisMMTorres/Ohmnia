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

As fontes aparecem agrupadas em **Fonte de tensão (CC/CA)** e **Fonte de corrente (CC/CA)**.
Nas propriedades, escolha o modo e a forma de onda (senoidal, quadrada ou triangular), com
amplitude pico a pico, offset, frequência e duty cycle. A onda triangular usa o duty como
fração do período dedicada à subida.

Em **Protoboard**, há duas placas e uma barra vertical de alimentação. O zoom inicial é 100%.

No esquemático, o zoom fica no canto superior direito do desenho: botões − e +, lista de níveis
(25 a 400 %) e **Ajustar** (enquadra o circuito). Atalhos: roda do mouse, `+`, `−`, `0` (100 %) e
`F` (ajustar).
**Colocar** insere o dispositivo inteiro; ajuste depois os terminais pelo painel. Furos da
segunda placa usam `2:`; os da barra vertical usam `vp` e `vn`. Os condutores só se unem por fios.
Use a conferência antes de simular: a vista Protoboard exige que a montagem corresponda ao esquema.

Em **Adicionar instrumento**, escolha **Fonte de bancada (3 canais)** para criar dois canais CC ajustáveis de −30 a +30 V
e um de 5 V fixos, com referência comum. As leituras de corrente vêm da simulação e ficam
indisponíveis após alterações elétricas até uma nova execução.

O mesmo seletor oferece **Gerador de sinais** e **Osciloscópio de 2 ou 4 canais**. Cada painel
possui um botão **Remover** para retirar o instrumento. A remoção da fonte retira os três
canais e suas probes geradas também do esquemático e da montagem. O osciloscópio pode ser
inserido antes da simulação e fica aguardando aquisição até haver resultados de ponto de operação ou transitórios.

Na fonte de bancada, **Canais em uso** permite manter apenas um ou dois canais, se necessário.
Somente os canais marcados aparecem como dispositivos na protoboard. Reativar um canal o
reinsere com seu valor inicial e terminais desconectados; Desfazer recupera uma retirada.

Cada canal possui seletores de **Terminal +** e **Terminal −** para escolher os furos da placa
ou da barra vertical. Também é possível clicar no borne do dispositivo desenhado e depois no
furo da protoboard. O cabo aparece no desenho; furos ocupados são rejeitados. Escolha outro furo
do mesmo barramento quando precisar compartilhar uma conexão elétrica.

Ao apagar um canal da fonte pelo botão **Apagar** ou pela tecla **Delete**, seus rótulos
automáticos e probes também são retirados. Rótulos automáticos que ficaram órfãos em versões
anteriores são limpos ao reabrir o circuito; rótulos manuais são preservados.

Ao abrir **Configurar análise** ou **Resultados** na vista Protoboard, os painéis de peças e
ponteiras ficam recolhidos para dar espaço à placa. Volte a **Circuito** para editá-los.
Em janelas estreitas, configuração e resultados aparecem abaixo da placa, sem cobri-la.

Nos resultados CC ou transitórios, **Osciloscópio de bancada** abre o instrumento didático de 2/4
canais. Selecione as probes de tensão, V/div, tempo/div, acoplamento e trigger. **Autoset**
enquadra a aquisição; **Stop** congela seus dados. Não há conexão com equipamento real.

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

O ponto de operação é exibido como uma linha horizontal de nível CC, com identificação de
valor estático, sem aquisição temporal. Tempo e trigger ficam desabilitados nesse modo.
O instrumento aceita probes de tensão e de corrente, com escala automática em V/div ou A/div.
Sem probes disponíveis, a interface orienta a conectar uma probe e simular novamente.
