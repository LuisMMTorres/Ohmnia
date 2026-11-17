# Bancada virtual e circuitos editáveis

Data: 2026-11-17. Branch: `codex/virtual-electronics-bench`.
Status: testado pelo usuário e aprovado para envio ao GitHub em 2026-11-17.

## Escopo solicitado

- Navegação: **Biblioteca**, **Análise de dispositivos** e **Análise de Projetos**.
- Simulador/Protoboard: duas placas, barra vertical de alimentação e zoom inicial de 100%.
- Inserção completa por **Colocar**, sem sequência obrigatória de cliques em furos.
- Fontes agrupadas por tensão/corrente, com CC e formas senoidal, quadrada e triangular.
- Fonte CC didática com dois canais de −30 a +30 V e canal fixo de 5 V.
- Osciloscópio didático com 2/4 canais; a marca citada pelo usuário é referência de interface,
  sem reprodução de modelo ou especificações de fabricante.
- Salvar como, editar componentes e enviar o circuito de um projeto para o Simulador.

## Regras elétricas e persistência

A placa 1 conserva os identificadores existentes (`a12`, `tp2`). A placa 2 usa o prefixo `2:`
(`2:a12`, `2:tp2`). As barras verticais são `vp1`…`vp40` e `vn1`…`vn40`. Placas e barras
permanecem isoladas até receberem jumpers explícitos. A conferência no backend usa as mesmas
regras do desenho, incluindo barramentos cortados. Arquivos antigos continuam abrindo.

**Colocar** insere a peça inteira em espaço livre; instrumentos e placas externas entram
inteiros, com terminais inicialmente desconectados. O painel de terminais permite escolher
os furos ou desconectar cada ligação. A conferência aponta o que ainda precisa ser ligado.
Isso não significa que um circuito inserido esteja automaticamente montado corretamente.

O osciloscópio aceita as probes de tensão e corrente da execução escolhida. Na protoboard, a ligação de
uma ponteira segue os barramentos e jumpers até um nó do esquemático; furos sem ligação e
ligações que unem nós diferentes são rejeitados. Após mudar conexões, reconecte a ponteira
e simule novamente. A simulação pela vista Protoboard exige aprovação da conferência;
o cálculo continua baseado no esquemático correspondente.

Os controles de fontes traduzem Vpp em amplitude de pico para SIN, ou em níveis mínimo/máximo
para PULSE. A onda triangular usa os tempos de subida/descida, com duty controlando a fração
de subida. Fontes existentes mantêm seus símbolos e parâmetros SPICE; PWL existente continua
editável pelos parâmetros avançados. A bancada de três canais usa três fontes ideais com
referência comum em 0; não representa isolamento entre canais nem limitação de corrente real.

A corrente mostrada vem da probe I da fonte e da análise OP ou do último ponto transitório,
com sinal de corrente fornecida. Após mudar o circuito, a leitura é invalidada até simular
novamente. Ausência de medição aparece como traço, nunca como uma corrente calculada fictícia.

**Análise de Projetos → Editar circuito do projeto** prepara um circuito físico editável.
A revisão do projeto guarda também o esquemático e a montagem. **Salvar como** cria outro
projeto; o original é preservado. Adição, retirada ou troca de componentes muda o circuito
editável, sem alterar as equações analíticas da topologia original. A verificação do circuito
livre deve ser feita em sua própria simulação. Histórico, duplicação e importação preservam
o circuito salvo; revisões antigas sem esse campo usam `null`.

## Instrumento de osciloscópio

Na aba Resultados de uma análise CC ou transitória, abra **Osciloscópio de bancada**:

- Modelo de 2 ou 4 canais, habilitação e seleção individual de ponteira.
- V/div, posição vertical, tempo/div, início da janela e Autoset.
- Acoplamento DC ou remoção da média (AC didático).
- Trigger de borda de subida/descida, nível e canal.
- Run/Stop para atualizar ou congelar os dados da aquisição simulada.

Não há aquisição de hardware nem especificações de banda, amostragem, impedância de entrada
ou proteção de um instrumento real. O gráfico usa apenas amostras da simulação.

## Validação

- Frontend: 50 testes unitários aprovados; TypeScript/build e ESLint aprovados.
- Backend: 29 testes de protoboard, propriedades e projetos aprovados.
- Navegador: os 13 cenários anteriores de simulação passaram, incluindo o divisor de 2,5 V.
  As verificações finais de navegação foram executadas separadamente após atualizar as
  expectativas dos nomes Biblioteca e Fonte de tensão (CC/CA).
- Novo fluxo de bancada aprovado: duas placas, inserção completa, terminais na placa 2 e barra
  vertical, três canais da fonte, probe ligada pela montagem, forma triangular conferida no
  ngspice, instrumento de 2/4 canais, leitura de corrente e cópia editada do projeto reaberta.
- Console do navegador sem erros no fluxo final. Ruff, ESLint, formatação e build aprovados.
- Novas regressões: isolamento das placas, conexão pela barra vertical, ponteiras em jumpers,
  rejeição de curto ambíguo, conversão das formas de onda e histórico do circuito editado.

## Como conferir

Reinicie pelo lançador local e atualize o navegador. Abra Simulador → Protoboard, insira peças,
ajuste os terminais e use a conferência. Use **Adicionar instrumento** para inserir a fonte de bancada, o gerador de sinais ou o
osciloscópio. Cada instrumento tem seu botão de remoção. Execute uma análise transitória para abrir o instrumento na aba Resultados.
Em Análise de Projetos, salve uma cópia, edite o circuito, salve e reabra para conferir as alterações.

## Ajuste: adicionar e remover instrumentos

O seletor **Adicionar instrumento** oferece fonte de bancada, gerador de sinais e osciloscópio
de 2 ou 4 canais. Fontes e geradores entram completos e com terminais desconectados, prontos
para conexão no painel. Cada painel tem um botão explícito de remoção. Remover uma fonte retira
seus canais, probes geradas, rótulos próprios e peças da montagem; as demais partes do circuito
são preservadas. Desfazer permite recuperar a alteração.

O osciloscópio pode ser inserido antes de simular, mostrando **Aguardando aquisição**. Quando
houver dados transitórios válidos, exibe os canais medidos diretamente na Protoboard. Sua presença
e escolha de 2/4 canais ficam guardadas no arquivo do circuito e nas revisões do projeto.

Regressões específicas verificam remoção sem peças residuais, inserção/remoção dos três tipos,
gerador com saída em tensão ou corrente, persistência do osciloscópio e uso de aquisição existente.
Os 7 testes de projetos foram reexecutados e aprovados com a persistência do instrumento.

## Ajuste: canais em uso e ligação das fontes

**Canais em uso** permite retirar e recolocar canais individuais, mantendo pelo menos um na
fonte. O botão Remover fonte continua retirando o instrumento inteiro. A retirada de um canal
preserva rótulos, probes e montagem dos demais; ao recolocar, o canal volta ao valor inicial
e fica desconectado. A presença dos canais fica guardada nos componentes do arquivo.

Os seletores de furos dos terminais +/− estão no painel de cada canal. A ligação também pode
ser iniciada pelo borne do dispositivo desenhado e concluída clicando num furo. O cabo e os
seletores acompanham a mesma conexão. Conflitos de ocupação são informados na interface.
Validação no navegador aprovada: reduzir de três para um canal, reativar o segundo mantendo
as conexões do primeiro, ligar os terminais pelo painel e mudar a ligação pelo borne e clique
num furo da segunda placa. Remoção dos instrumentos e persistência também passaram.

## Ajustes: exclusão no esquemático e espaço da protoboard

O botão Apagar e a tecla Delete usam a mesma remoção de instrumentos, retirando rótulos
automáticos, probes e peças da montagem. Rótulos automáticos órfãos de versões anteriores
são reconhecidos pelos identificadores e limpos ao carregar; rótulos manuais são preservados.

Na vista Protoboard, configuração e resultados usam uma coluna reservada à placa e outra ao
painel selecionado. Peças, ponteiras e conferência voltam a aparecer ao selecionar Circuito.
Em janelas menores, os resultados ficam abaixo da placa. O zoom da protoboard é preservado.
Testes de navegador aprovados para exclusão pelo botão e teclado, limpeza de tags antigas,
simulação pela protoboard, largura útil em 1600 px, disposição em 900 px e retorno dos controles.

## Limitações conhecidas

- A montagem automática continua priorizando a primeira placa; a segunda está disponível para
  montagem e redistribuição manual.
- Instrumentos têm representação vetorial didática, sem fotografias de equipamentos reais.
- Edição livre não recalcula automaticamente os resultados analíticos do módulo de projeto.
- O build mantém o aviso existente de pacote JavaScript acima de 500 kB.

## Correção: sinal CC no osciloscópio

O instrumento aceita ponto de operação (.op), além de transitória. O valor escalar real da
simulação é representado como nível horizontal, com indicação explícita de valor CC estático.
Não são criadas amostras temporais fictícias; controles de tempo e trigger ficam desabilitados.
A leitura numérica do canal permite conferir a tensão. Em acoplamento AC, o componente CC é removido.
Tensão e corrente usam suas unidades reais e escalas V/div ou A/div.
Se não houver probe disponível, uma orientação substitui a ausência silenciosa de traços.
Verificação no navegador aprovada com divisor de 2,5 V em ponto de operação e transitória,
corrente CC de 2,5 mA em módulo, além da orientação quando não há probes. O gráfico foi
conferido tanto no instrumento da Protoboard quanto na aba de resultados do ponto de operação.

## Miniatura conectável do osciloscópio

O instrumento é representado na mesma área das fontes por uma miniatura com dois bornes (+/−)
por canal. Clique num borne e depois no furo da placa. O cabo assume a cor do canal; a referência
usa traço descontínuo. A ligação fica salva no circuito e nas revisões do projeto.

Canais com duas ponteiras conectadas geram probes diferenciais próprias. A simulação resolve
novamente os nós a partir dos furos e jumpers atuais, evitando reutilizar uma leitura de ligação
antiga. Furos sem ligação ou que unem nós incompatíveis são rejeitados. O instrumento é ideal,
sem carregar o circuito; referências diferentes entre canais não simulam o curto de um equipamento
real com terras comuns. Desconectar ou remover o instrumento retira suas probes geradas.

A seleção de sinal do instrumento fica vinculada aos canais fisicamente conectados. As configurações
de escala, posição e acoplamento permanecem no painel. Arquivos anteriores sem ligações de miniatura
continuam aceitando as probes existentes até que sejam conectadas ponteiras na miniatura.

Testes: 50 testes do frontend; 10 testes de conexões/persistência no backend; 14 testes de expressões.
Foi corrigido também o formato vetorial de resultados escalares constantes sem eixo temporal,
necessário para entregar corretamente a medição de 0 V com ambas as ponteiras no mesmo nó.
Validação no navegador aprovada: miniatura de quatro canais, conexão dos dois bornes pelo clique
nos furos, persistência após recarregar, leitura de 2,5 V, mudança da ponteira para 0 V, desconexão
e remoção do instrumento sem probes residuais. A exclusão da probe pelo esquemático também
desconecta o canal correspondente, preservando a consistência com os cabos desenhados.
