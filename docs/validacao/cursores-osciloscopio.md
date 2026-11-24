# Cursores do osciloscópio de bancada

Entrega de 23/11/2026. O instrumento de 2/4 canais passa a oferecer cursores de tempo e
amplitude, tanto nos resultados quanto no instrumento adicionado à protoboard.

## Como usar

1. Simule um circuito com probes de tensão/corrente e abra **Resultados → Osciloscópio de bancada**.
2. Em **Cursores de medição**, ative **Tempo A/B**, **Amplitude A/B** ou ambos.
3. Arraste as linhas tracejadas ou preencha os campos numéricos, em segundos ou na unidade
   do canal. **Reposicionar cursores** coloca as linhas novamente dentro da janela atual.
4. Os cursores de tempo mostram A, B, `Δt = B − A`, `1/|Δt|` e os valores de cada canal
   nos dois instantes. Cada linha da tabela inclui sua diferença de amplitude.
5. Os cursores horizontais usam o **Canal de referência**, incluindo sua escala e posição.
   A tabela também compara os canais com a referência em A/B, somente para unidades iguais.

Os valores têm até sete algarismos significativos, com unidades e notação de engenharia.
Arrastar preserva o eixo escolhido, inclusive quando o gráfico é redimensionado.
Escala e posição vertical modificam apenas o desenho, não a amplitude física medida.
Acoplamento AC mede o sinal exibido após remover a média da aquisição, como o instrumento
já fazia para os traços. Ao trocar o sinal, a unidade ou o acoplamento da referência,
os cursores horizontais são reposicionados para evitar reutilizar valores incompatíveis.

Ponto de operação CC oferece cursores de amplitude e leitura dos níveis dos canais ativos.
O controle de tempo fica desabilitado: essa análise não contém uma aquisição temporal.

## Precisão e limites

- Os valores em instantes intermediários usam interpolação linear das amostras da simulação.
  Não representam precisão adicional à do solver nem resolvem descontinuidades entre amostras.
- Fora da aquisição, o canal mostra `—`, sem extrapolar. Valores ausentes/não finitos também
  não geram uma leitura numérica falsa.
- Ativar os cursores solicita até dois milhões de pontos por sinal, em vez dos dez mil
  usados normalmente para desenhar. Acima desse limite há um aviso de amostras reduzidas.
- Durante essa solicitação há um indicador de carregamento. Convém aguardar seu término
  antes de anotar a leitura. Ajustar escala, posição ou arrastar cursores não refaz a busca.
- `Δt = 0` não produz uma frequência infinita. `1/|Δt|` só corresponde à frequência do sinal
  quando o intervalo escolhido representa um período.
- Os cursores deste instrumento são independentes dos cursores simples do gráfico uPlot
  na aba **Osciloscópio**, que continuam com o comportamento anterior.

## Validação

- Suíte completa do frontend: **78 testes aprovados** na implementação inicial.
  Após atualizar a base com o PR #22: **79 aprovados**, build TypeScript/Vite e ESLint.
- Testes matemáticos: grade temporal adaptativa, interpolação, deltas negativos, bordas,
  ausência de dados, CC, acoplamento AC e conversão de coordenadas com escala/posição.
- Chrome, com simulação real ngspice: fonte PWL de 0 → 2 → −2 → 0 V e divisor resistivo
  de duas resistências genéricas de 1 kΩ. Em A = 1 ms e B = 3 ms:
  CH1 = 2/−2 V, CH2 = 1/−1 V, Δt = 2 ms, deltas de −4/−2 V e comparação CH2−CH1 = −1/1 V.
- Conferidos entrada numérica, dois arrastes independentes, Δt zero, referência CH2,
  quatro canais, redimensionamento para 700 px e CC de 2,5 V com divisor de tensão.
- Contraste da tabela inspecionado visualmente no instrumento escuro.

Exemplo reproduzível: `frontend/e2e/fixtures/scope-cursors.json`, aberto no Simulador.
Teste de navegador: `frontend/e2e/scope-cursors.e2e.cjs`, com `BASE` apontando para o servidor
e Playwright disponível no ambiente. `PROJECT` permite trocar o exemplo e
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` seleciona o Chrome instalado.

Sem alterações no backend ou no solver; não foi necessário repetir sua suíte.
